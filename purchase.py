# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
# from trytond.transaction import Transaction
from trytond.modules.stock_reservation.stock import delete_related_reservations


__all__ = ['PurchaseLine', 'Purchase', 'PurchaseRequest']
__metaclass__ = PoolMeta

class Purchase:
    __name__ = 'purchase.purchase'
    sales = fields.Function(fields.One2Many('sale.sale', None, 'Sales'),
        'get_sales', searcher='search_sales')

    def get_sales(self, name):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        SaleLine = pool.get('sale.line')
        ShipmentOut = pool.get('stock.shipment.out')
        sales = set()
        reservations = []

        def get_recursive_moves(moves, processed_moves=None):
            if not moves:
                return []
            if processed_moves is None:
                processed_moves = set()

            reservations = Reservation.search([
                    ('source', 'in', moves),
                    ])
            new_moves = set([x.destination for x in
                    reservations if x.destination])
            for move in moves:
                if move.id in processed_moves:
                    continue
                if move.production_input:
                    new_moves |= set(move.production_input.outputs)
                processed_moves.add(move.id)

            reservations += get_recursive_moves(list(new_moves),
                processed_moves)

            return reservations

        moves = []
        for shipment in self.shipments + self.shipment_returns:
            moves += shipment.inventory_moves
        reservations = get_recursive_moves(moves)

        direct_reservations = Reservation.search([
                ('source_document', 'in', [str(l) for l in self.lines]),
                ])

        reservations += direct_reservations
        reservations += get_recursive_moves([x.destination for x in
                direct_reservations if x.destination])

        for reservation in reservations:
            if reservation.destination:
                if reservation.destination.origin:
                    origin = reservation.destination.origin
                    if isinstance(origin, SaleLine):
                        sales.add(origin.sale)
            if reservation.destination_document:
                dest_move = reservation.destination
                shipment = reservation.destination_document
                if isinstance(shipment, ShipmentOut):
                    for move in shipment.outgoing_moves:
                        if not move.product == dest_move.product:
                            continue
                        if move.origin and isinstance(move.origin,
                                SaleLine):
                            sales.add(move.origin.sale)

        return [s.id for s in sales]

    @classmethod
    def search_sales(cls, name, clause):
        pool = Pool()
        Sale = pool.get('sale.sale')
        purchases = set()
        for sale in Sale.search([('id',) + tuple(clause[1:])]):
            for purchase in sale.purchases:
                purchases.add(purchase.id)
        return [('id', 'in', purchases)]


class PurchaseRequest:
    __name__ = 'purchase.request'
    sales = fields.Function(fields.One2Many('sale.sale', None, 'Sales'),
        'get_sales', searcher='search_sales')

    def get_sales(self, name):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        SaleLine = pool.get('sale.line')
        ShipmentOut = pool.get('stock.shipment.out')
        sales = set()
        reservations = []

        def get_recursive_moves(moves, processed_moves=None):
            if not moves:
                return []
            if processed_moves is None:
                processed_moves = set()

            reservations = Reservation.search([
                    ('source', 'in', moves),
                    ])
            new_moves = set([x.destination for x in
                    reservations if x.destination])
            for move in moves:
                if move.id in processed_moves:
                    continue
                if move.production_input:
                    new_moves |= set(move.production_input.outputs)
                processed_moves.add(move.id)

            reservations += get_recursive_moves(list(new_moves),
                processed_moves)

            return reservations

        direct_reservations = Reservation.search([
                ('source_document', '=', str(self))])

        reservations = direct_reservations
        reservations += get_recursive_moves([x.destination for x in
                direct_reservations if x.destination])


        for reservation in reservations:
            if reservation.destination:
                if reservation.destination.origin:
                    origin = reservation.destination.origin
                    if isinstance(origin, SaleLine):
                        sales.add(origin.sale)
            if reservation.destination_document:
                dest_move = reservation.destination
                shipment = reservation.destination_document
                if isinstance(shipment, ShipmentOut):
                    for move in shipment.outgoing_moves:
                        if not move.product == dest_move.product:
                            continue
                        if move.origin and isinstance(move.origin,
                                SaleLine):
                            sales.add(move.origin.sale)

        return [s.id for s in sales]



    @classmethod
    def search_sales(cls, name, clause):
        pool = Pool()
        Sale = pool.get('sale.sale')
        requests = set()
        for sale in Sale.search([('id',) + tuple(clause[1:])]):
            for request in sale.purchase_requests:
                requests.add(request.id)
        return [('id', 'in', requests)]

    @classmethod
    def write(cls, *args):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        actions = iter(args)
        super(PurchaseRequest, cls).write(*args)
        for requests, value in zip(actions, actions):
            if 'purchase_line' in value:
                reserves = Reservation.search([
                        ('state', 'in', ['draft', 'waiting']),
                        ('source_document', 'in', [str(r) for r in requests]),
                        ])
                if reserves:
                    Reservation.write(reserves, {
                            'source_document': ('purchase.line,%d' %
                                value.get('purchase_line')),
                            })

    @classmethod
    def delete(cls, requests):
        delete_related_reservations(requests, 'source_document')
        super(PurchaseRequest, cls).delete(requests)


class PurchaseLine:
    __name__ = 'purchase.line'

    purchase_date = fields.Function(fields.Date('Purchase Date'),
        'get_purchase_date')

    def get_purchase_date(self, name):
        if self.purchase:
            return self.purchase.purchase_date

    @staticmethod
    def order_purchase_date(tables):
        pool = Pool()
        Purchase = pool.get('purchase.purchase')
        line, _ = tables[None]
        if 'purchase' not in tables:
            purchase = Purchase.__table__()
            tables['purchase'] = {
                None: (purchase, line.purchase == purchase.id),
                }
        else:
            purchase = tables['purchase']
        return Purchase.purchase_date.convert_order('purchase_date',
            tables['purchase'], Purchase)

    @classmethod
    def delete(cls, lines):
        delete_related_reservations(lines, 'source_document')
        super(PurchaseLine, cls).delete(lines)
