# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from datetime import datetime
from sql import Literal, Cast
from sql.operators import Concat
from sql.conditionals import Case

from trytond.model import Workflow, Model, ModelSQL, ModelView, fields
from trytond.report import Report
from trytond.pyson import Eval, If, In
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateAction, StateTransition, \
    Button
from trytond.tools import reduce_ids
from trytond.rpc import RPC


__all__ = ['Reservation', 'WaitReservation', 'WaitReservationStart',
    'CreateReservations', 'CreateReservationsStart',
    'PrintReservationGraphStart', 'PrintReservationGraph', 'ReservationGraph',
    'Move', 'PurchaseLine', 'Production', 'Sale',
    'ShipmentOut', 'ShipmentOutReturn', 'ShipmentIn', 'ShipmentInternal',
    'Purchase', 'PurchaseRequest']
__metaclass__ = PoolMeta

STATES = {
    'readonly': Eval('state') != 'draft',
}
DEPENDS = ['state']


def delete_related_reservations(records, field):
    assert field in ('source_document', 'destination_document')
    pool = Pool()
    Reservation = pool.get('stock.reservation')
    reserves = Reservation.search([
            (field, 'in', [str(r) for r in records]),
            ])
    if reserves:
        Reservation.delete(reserves)


class Reservation(Workflow, ModelSQL, ModelView):
    "Stock Reservation"
    __name__ = 'stock.reservation'

    company = fields.Many2One('company.company', 'Company', required=True,
        states=STATES, depends=DEPENDS,
        domain=[
            ('id', If(In('company', Eval('context', {})), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ])
    product = fields.Many2One("product.product", "Product", required=True,
        select=True, states=STATES,
        domain=[
            ('type', '!=', 'service'),
            ],
        depends=DEPENDS)
    uom = fields.Many2One("product.uom", "Uom", required=True, states=STATES,
        depends=DEPENDS)
    unit_digits = fields.Function(fields.Integer('Unit Digits'),
        'on_change_with_unit_digits')
    quantity = fields.Float("Quantity", required=True,
        digits=(16, Eval('unit_digits', 2)), states=STATES,
        depends=['state', 'unit_digits'])
    internal_quantity = fields.Function(fields.Float('Internal Quantity',
            digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'],
            help='Quantity in product default UOM'),
        'on_change_with_internal_quantity')
    source_document = fields.Reference('Source',
        selection='get_source_document', states=STATES, depends=DEPENDS)
    location = fields.Many2One('stock.location', 'Location', select=True,
        required=True, domain=[('type', 'in', ['storage', 'production'])],
        states=STATES, depends=DEPENDS)
    destination = fields.Many2One('stock.move', 'Destination Move',
        select=True,
        states={
            'readonly': (Eval('state') != 'draft') | ~Eval('location'),
            'required': Eval('state') == 'done',
            },
        depends=['state', 'location', 'product', 'source_to_location'],
        domain=[
            (If(Eval('state') == 'draft', ('state', '=', 'draft'), ())),
            ('product', '=', Eval('product', -1)),
            ('from_location', '=', Eval('location', -1)),
            ],
        ondelete='CASCADE')
    destination_document = fields.Function(fields.Reference('Destination',
        selection='get_destination_document_selection'),
        'get_destination_document', searcher='search_destination_document')
    destination_planned_date = fields.Function(fields.Date('Planned Date'),
        'get_move_field')
    destination_from_location = fields.Function(fields.Many2One(
            'stock.location', 'From Location'),
        'get_move_field')
    destination_to_location = fields.Function(fields.Many2One(
            'stock.location', 'To Location'),
        'get_move_field')
    get_from_stock = fields.Boolean('Get from stock')
    source = fields.Many2One('stock.move', 'Source Move', select=True,
        states={
            'readonly': (Eval('state') != 'draft') | ~Eval('location'),
            'required': ((Eval('state') == 'done') &
                ~Eval('get_from_stock', False)),
            'invisible': Eval('get_from_stock', False),
            },
        depends=['state', 'location', 'product', 'get_from_stock'],
        domain=[
            (If(Eval('state') == 'draft', ('state', '=', 'draft'), ())),
            ('product', '=', Eval('product', -1)),
            ('to_location', '=', Eval('location', -1)),
            ],
        ondelete='CASCADE')
    source_planned_date = fields.Function(fields.Date('Planned Date',
            states={
                'invisible': Eval('get_from_stock', False),
                },
            depends=['get_from_stock']),
        'on_change_with_source_planned_date')
    source_from_location = fields.Function(fields.Many2One('stock.location',
            'From Location',
            states={
                'invisible': Eval('get_from_stock', False),
                },
            depends=['get_from_stock']),
        'get_move_field')
    source_to_location = fields.Function(fields.Many2One('stock.location',
            'To Location',
            states={
                'invisible': Eval('get_from_stock', False),
                },
            depends=['get_from_stock']),
        'get_move_field')
    failed_reason = fields.Selection([
            (None, ''),
            ('source_canceled', 'Source Move was canceled'),
            ('destination_canceled', 'Destination Move was canceled'),
            ], 'Failing Reason', readonly=True)
    failed_date = fields.DateTime('Failed Date', readonly=True)
    state = fields.Selection([
            ('draft', 'Draft'),
            ('waiting', 'Waiting'),
            ('failed', 'Failed'),
            ('done', 'Done'),
            ], 'State', select=True, readonly=True)
    reserve_type = fields.Function(fields.Selection([
                ('exceeding', 'Exceeding'),
                ('pending', 'To be Assigned'),
                ('on_time', 'Assigned On Time'),
                ('delayed', 'Assigned Delayed'),
                ('in_stock', 'In Stock'),
                ], 'Reserve Type'),
        'get_reserve_type', searcher='search_reserve_type')
    warning_color = fields.Function(fields.Selection([
                ('black', 'Ok (Black)'),
                ('red', 'Reservation in past (Red)'),
                ], 'Warning Color'),
        'get_warning_color')
    day_difference = fields.Function(fields.Integer('Day Difference'),
        'get_day_difference', searcher='search_day_difference')
    supplier_shipments = fields.Function(fields.One2Many('stock.shipment.in',
            None, 'Supplier Shipments'), 'get_supplier_shipments')
    supplier_return_shipments = fields.Function(fields.One2Many(
            'stock.shipment.in.return', None, 'Supplier Return Shipments'),
        'get_supplier_return_shipments')
    customer_shipments = fields.Function(fields.One2Many('stock.shipment.out',
            None, 'Customer Shipments'), 'get_customer_shipments')
    customer_return_shipments = fields.Function(fields.One2Many(
            'stock.shipment.out.return', None, 'Customer Return Shipments'),
        'get_customer_return_shipments')
    internal_shipments = fields.Function(fields.One2Many(
            'stock.shipment.internal', None, 'Internal Shipments'),
        'get_internal_shipments')
    productions = fields.Function(fields.One2Many('production',
            None, 'Productions'), 'get_productions')
    sales = fields.Function(fields.One2Many('sale.sale',
            None, 'Sales'), 'get_sales', searcher='search_sales')
    purchases = fields.Function(fields.One2Many('purchase.purchase',
            None, 'Purchases'), 'get_purchases', searcher='search_purchases')
    purchase_requests = fields.Function(fields.One2Many('purchase.request',
            None, 'Purchase Requests'), 'get_related_purchase_requests',
        searcher='search_purchase_requests')

    @classmethod
    def __setup__(cls):
        super(Reservation, cls).__setup__()
        cls._error_messages.update({
            'delete_draft': ('You can not delete stock reservation "%s" '
                    'because it is not in draft state.'),
            'reservation_overpass_move': ('Reservation "%s" overpasses Move '
                    '"%s" quantity.'),
                })
        cls._transitions |= set((
                ('draft', 'waiting'),
                ('waiting', 'draft'),
                ('waiting', 'failed'),
                ('waiting', 'done'),
                ('done', 'draft'),
                ))
        cls._buttons.update({
                'draft': {
                    'invisible': ~Eval('state').in_(['waiting']),
                    },
                'wait': {
                    'invisible': ~Eval('state').in_(['draft']),
                    },
                'fail': {
                    'invisible': ~Eval('state').in_(['waiting']),
                    },
                'do': {
                    'invisible': ~Eval('state').in_(['waiting']),
                    },
                })
        cls.__rpc__.update({
                'get_destination_document_selection': RPC(),
                })

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_unit_digits():
        return 2

    @fields.depends('uom')
    def on_change_with_unit_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    @fields.depends('uom', 'product', 'quantity')
    def on_change_with_internal_quantity(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if self.uom and self.product and self.quantity:
            return Uom.compute_qty(self.uom, self.quantity,
                self.product.default_uom)

    def get_move_field(self, name):
        move_name, field_name = name.split('_', 1)
        move = getattr(self, move_name)
        if not move:
            return
        res = getattr(move, field_name)
        if hasattr(res, 'id'):
            return res.id
        return res

    @fields.depends('destination')
    def on_change_with_destination_planned_date(self, name=None):
        return self.get_move_field('destination_planned_date')

    @fields.depends('destination')
    def on_change_with_destination_to_location(self, name=None):
        return self.get_move_field('destination_to_location')

    @fields.depends('destination')
    def on_change_with_destination_from_location(self, name=None):
        return self.get_move_field('destination_from_location')

    @fields.depends('source', 'source_document')
    def on_change_with_source_planned_date(self, name=None):
        pool = Pool()
        PurchaseRequest = pool.get('purchase.request')
        PurchaseLine = pool.get('purchase.line')
        if self.source_document:
            if isinstance(self.source_document, PurchaseLine):
                return self.source_document.delivery_date
            elif isinstance(self.source_document, PurchaseRequest):
                return self.source_document.supply_date
        return self.get_move_field('source_planned_date')

    @fields.depends('source')
    def on_change_with_source_to_location(self, name=None):
        return self.get_move_field('source_to_location')

    @fields.depends('source')
    def on_change_with_source_from_location(self, name=None):
        return self.get_move_field('source_from_location')

    @fields.depends('product')
    def on_change_product(self):
        res = {}
        if self.product:
            res['uom'] = self.product.default_uom.id
            res['uom.rec_name'] = self.product.default_uom.rec_name
            res['unit_digits'] = self.product.default_uom.digits
        return res

    def get_rec_name(self, name):
        return "%d %s %s @ %s" % (self.quantity, self.uom.symbol,
            self.product.name, self.location.rec_name)

    @classmethod
    def _get_source_document(cls):
        'Return list of Model names for source_document Reference'
        return [
            'stock.shipment.in',
            'stock.shipment.out.return',
            'stock.shipment.internal',
            'production',
            'purchase.request',
            'purchase.line',
            ]

    @classmethod
    def get_source_document(cls):
        pool = Pool()
        Model = pool.get('ir.model')
        models = cls._get_source_document()
        models = Model.search([
                ('model', 'in', models),
                ])
        return [('', '')] + [(m.model, m.name) for m in models]

    @classmethod
    def _get_destination_document_models(cls):
        'Return list of Model names for destination_document Reference'
        return [
            'stock.shipment.out',
            'stock.shipment.in.return',
            'stock.shipment.internal',
            'production',
            ]

    @classmethod
    def get_destination_document_selection(cls):
        pool = Pool()
        Model = pool.get('ir.model')
        models = cls._get_destination_document_models()
        models = Model.search([
                ('model', 'in', models),
                ])
        return [('', '')] + [(m.model, m.name) for m in models]

    def get_destination_document(self, name):
        if not self.destination:
            return None
        if self.destination.production_input:
            return str(self.destination.production_input)
        if self.destination.production_output:
            return str(self.destination.production_output)
        if self.destination.shipment:
            return str(self.destination.shipment)
        return ''

    def get_shipments(model_name):
        "Computes the returns or shipments"
        def method(self, name):
            Model = Pool().get(model_name)
            shipments = set()
            for move in (self.source, self.destination):
                if not move:
                    continue
                if isinstance(move.shipment, Model):
                    shipments.add(move.shipment.id)
            return list(shipments)
        return method

    get_supplier_shipments = get_shipments('stock.shipment.in')
    get_supplier_return_shipments = get_shipments('stock.shipment.in.return')
    get_customer_shipments = get_shipments('stock.shipment.out')
    get_customer_return_shipments = get_shipments('stock.shipment.out.return')
    get_internal_shipments = get_shipments('stock.shipment.internal')

    def get_productions(self, name):
        productions = set()
        for move in self.source, self.destination:
            if not move:
                continue
            if move.production_input:
                productions.add(move.production_input.id)
            if move.production_output:
                productions.add(move.production_output.id)
        return list(productions)

    def get_sales(self, name):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        shipments = self.customer_shipments + self.customer_return_shipments
        move_ids = []
        for shipment in shipments:
            move_ids.extend([x.id for x in shipment.outgoing_moves])

        with Transaction().set_user(0, set_context=True):
            sale_lines = SaleLine.search([
                    ('moves', 'in', move_ids),
                    ])
            if sale_lines:
                return list(set(l.sale.id for l in sale_lines))
        return []

    def get_reserve_type(self, name):
        if self.get_from_stock:
            return 'in_stock'
        if (self.source or self.source_document) and not self.destination:
            return 'exceeding'
        if self.destination and not (self.source or self.source_document):
            return 'pending'
        if self.day_difference and self.day_difference < 0:
            return 'delayed'
        return 'on_time'

    def get_warning_color(self, name):
        Date = Pool().get('ir.date')
        today = Date.today()
        if (self.state in ('draft', 'waiting') and
                self.destination_planned_date
                and self.destination_planned_date < today):
            return 'red'
        return 'black'

    def get_day_difference(self, name):
        name = 'planned_date'
        if self.state == 'done':
            name = 'effective_date'
        if self.source and self.destination:
            source = getattr(self.source, name)
            destination = getattr(self.destination, name)
            if source and destination:
                return (destination - source).days

    def get_purchases(self, name):
        pool = Pool()
        PurchaseLine = pool.get('purchase.line')
        shipments = self.supplier_shipments + self.supplier_return_shipments
        move_ids = []
        for shipment in shipments:
            move_ids.extend([x.id for x in shipment.outgoing_moves])

        res = []
        with Transaction().set_user(0, set_context=True):
            purchase_lines = PurchaseLine.search([
                    ('moves', 'in', move_ids),
                    ])
            if purchase_lines:
                res.extend(list(set(l.purchase for l in purchase_lines)))
        if self.origin and isinstance(self.origin, PurchaseLine):
            res.append(self.origin.purchase.id)
        return res

    def get_related_purchase_requests(self, name):
        pool = Pool()
        Request = pool.get('purchase.request')
        res = []
        if self.origin and isinstance(self.origin, Request):
            res.append(self.origin.purchase.id)
        return res

    @classmethod
    def search_reserve_type(cls, name, clause):
        reservation = cls.__table__()
        Operator = fields.SQL_OPERATORS[clause[1]]

        day_difference = cls.search_day_difference('day_difference',
            ('day_difference', '<', 0))
        _, _, date_query = day_difference[0]

        query = reservation.select(reservation.id,
            where=(Operator(Case(
                        (reservation.get_from_stock, Literal('in_stock')),
                        ((((reservation.source != None) |
                                    (reservation.source_document != None))
                                & (reservation.destination == None)),
                            Literal('exceeding')),
                        (((reservation.source == None) &
                                    (reservation.source_document == None) &
                                (reservation.destination != None)),
                            Literal('pending')),
                        (reservation.id.in_(date_query), Literal('delayed')),
                        else_=Literal('on_time')), clause[2])))

        return [('id', 'in', query)]

    @classmethod
    def search_destination_document(cls, name, clause):
        pool = Pool()
        Move = pool.get('stock.move')
        destination = Move.__table__()
        reservation = cls.__table__()

        Operator = fields.SQL_OPERATORS[clause[1]]
        Char = cls.state.sql_type().base
        value = clause[2]
        if isinstance(value, list):
            if clause[1] in ('in', 'not in'):
                value = [str(x) for x in value]
            else:
                value = ','.join([str(x) for x in value])
        query = reservation.join(destination, condition=(
                destination.id == reservation.destination)).select(
                    reservation.id,
            where=(Operator(Case(
                        ((destination.shipment != None),
                            destination.shipment),
                        ((destination.production_input != None) &
                            Concat(Literal('production,'), Cast(
                                            destination.production_input,
                                            Char))),
                        ((destination.production_output != None) &
                            Concat(Literal('production,'), Cast(
                                            destination.production_output,
                                            Char))),
                        ), value)))
        return [('id', 'in', query)]

    @classmethod
    def search_sales(cls, name, clause):
        pool = Pool()
        Move = pool.get('stock.move')
        moves = Move.search([('sale',) + tuple(clause[1:])])
        shipments = list(set([m.shipment for m in moves if m.shipment]))
        return [('destination_document', 'in', shipments)]

    @classmethod
    def search_day_difference(cls, name, clause):
        pool = Pool()
        Move = pool.get('stock.move')
        reservation = cls.__table__()
        source = Move.__table__()
        destination = Move.__table__()
        Operator = fields.SQL_OPERATORS[clause[1]]
        query = reservation.join(source, condition=(
                reservation.source == source.id)).join(destination, condition=(
                        reservation.destination == destination.id)).select(
                            reservation.id, where=(Operator((
                                    destination.planned_date -
                                        source.planned_date), clause[2])
                                    ))
        return [('id', 'in', query)]

    @classmethod
    def search_purchases(cls, name, clause):
        return [tuple(('source_document.purchase',)) + tuple(clause[1:]) +
            tuple(('purchase.line',))]

    @classmethod
    def search_purchase_requests(cls, name, clause):
        return [tuple(('source_document.id',)) + tuple(clause[1:]) +
            tuple(('purchase.request',))]

    @classmethod
    def delete(cls, reservations):
        for reserve in reservations:
            if reserve.state != 'draft':
                cls.raise_user_error('delete_draft', (reserve.rec_name,))
        super(Reservation, cls).delete(reservations)

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, reservations):
        pool = Pool()
        Move = pool.get('stock.move')

        moves = ([r.source for r in reservations
                if r.source and r.state != 'done'] +
            [r.destination for r in reservations
                if r.destination and r.state != 'done'])
        with Transaction().set_context(stock_reservation=True):
            Move.draft(moves)

    @classmethod
    @ModelView.button
    @Workflow.transition('waiting')
    def wait(cls, reservations):
        pass
        #TODO: Determine when to split moves
#        for reservation in reservations:
#            reservation.split_moves('waiting')

    @classmethod
    @ModelView.button
    @Workflow.transition('failed')
    def fail(cls, reservations):
        pool = Pool()
        Move = pool.get('stock.move')
        moves = []
        for reservation in reservations:
            if reservation.source.state == 'assigned':
                moves.append(reservation.source)
            if reservation.destination.state == 'assigned':
                moves.append(reservation.destination)
        with Transaction().set_context(stock_reservation=True):
            Move.draft(moves)

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def do(cls, reservations):
        pool = Pool()
        Move = pool.get('stock.move')

        to_assign = []
        to_do = []
        for reservation in reservations:
            #TODO: Determine when to split moves
#           reservation.split_moves('done')
            if reservation.source and reservation.source.state == 'assigned':
                to_do.append(reservation.source)
            if reservation.destination.state == 'draft':
                to_assign.append(reservation.destination)

        cls.write(reservations, {'state': 'done'})
        if to_assign:
            Move.assign(to_assign)
        if to_do:
            Move.do(to_do)

    def split_moves(self, next_state):
        """
        Splits the moves (by quantity) if needed.
        Next stage is used to determine which move must be splited
        """
        assert next_state in ('waiting', 'done')
        pool = Pool()
        Move = pool.get('stock.move')
        Uom = pool.get('product.uom')

        move_name = 'source' if next_state == 'waiting' else 'destination'
        move = getattr(self, move_name)
        if not move:
            return
        #TODO: This should be moved to check_* method? Currently is not called
        move_qty = Uom.compute_qty(move.uom, move.quantity, self.uom)
        if move_qty < self.quantity:
            self.raise_user_error('reservation_overpass_move', (self.rec_name,
                move.rec_name))
        if move_qty > self.quantity:
            remaining_quantity = move_qty - self.quantity
            new_move, = Move.copy([move], {'quantity': remaining_quantity})
            move.quantity = self.quantity
            move.uom = self.uom
            move.save()
            reservations = self.search([
                    (move_name, '=', move),
                    ('id', '!=', self.id),
                    ])
            if reservations:
                self.write(reservations, {move_name: new_move})

    @classmethod
    def generate_reservations(cls, clean=True):
        """
        Compute all available reservations based on draft stock moves.

        If clean is set, it will remove all previous reservations.
        """
        pool = Pool()
        Date = pool.get('ir.date')
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        PurchaseLine = pool.get('purchase.line')
        PurchaseRequest = pool.get('purchase.request')
        Uom = pool.get('product.uom')

        if clean:
            reservations = cls.search([
                    ('state', '=', 'draft'),
                    ])
            cls.delete(reservations)

        destination_moves = cls.get_destination_moves()

        location_ids = [l.id for l in Location.search([
                    ('type', '=', 'storage')])]
        product_ids = list(set([m.product.id for m in destination_moves]))
        with Transaction().set_context(stock_assign=True,
                stock_date_end=Date.today()):
            pbl = Product.products_by_location(location_ids, product_ids)

        consumed_quantities = {}
        for reservation in cls.search([
                    ('state', 'not in', ['done', 'failed']),
                    ]):
            if reservation.get_from_stock:
                key = (reservation.destination.from_location.id,
                    reservation.destination.product.id)
                pbl[key] -= reservation.internal_quantity

            for name in ('source', 'destination'):
                move = getattr(reservation, name, None)
                if not move:
                    continue
                key = (name, move.id,)
                if not key in consumed_quantities:
                    consumed_quantities[key] = 0
                #TODO: Currently not converting uom.
                consumed_quantities[key] += reservation.internal_quantity
            source_document = reservation.source_document
            if source_document:
                key = None
                if isinstance(source_document, PurchaseLine):
                    key = ('purchase_line', source_document.id,)
                elif isinstance(source_document, PurchaseRequest):
                    key = ('purchase_request', source_document.id,)
                if key:
                    if not key in consumed_quantities:
                        consumed_quantities[key] = 0
                    consumed_quantities[key] += reservation.internal_quantity

        requests = cls.get_purchase_requests()
        purchase_lines = cls.get_purchase_lines()

        warehouses = Location.search([
                ('type', '=', 'warehouse'),
                ])
        default_warehouse_location = (warehouses[0].storage_location
            if len(warehouses) == 1 else None)

        to_create = []
        for destination in destination_moves:
            quantity = destination.internal_quantity
            reserved_quantity = consumed_quantities.get(('destination',
                    destination.id,), 0.0)
            quantity -= reserved_quantity

            if quantity <= 0.0:
                continue

            # Create reservation from stock
            key = (destination.from_location.id, destination.product.id,)
            stock_quantity = min(pbl.get(key, 0.0),
                destination.internal_quantity)
            if stock_quantity > 0.0:
                reservation = cls.get_reservation(None, destination,
                    stock_quantity, destination.product.default_uom)
                reservation.get_from_stock = True
                pbl[key] -= stock_quantity
                to_create.append(reservation._save_values)
                quantity -= stock_quantity

            if quantity <= 0.0:
                continue

            # Create reservation from other moves
            for source in cls.get_source_moves(destination):
                key = ('source', source.id,)
                consumed_quantity = consumed_quantities.get(key, 0.0)
                remaining_quantity = (source.internal_quantity -
                    consumed_quantity)

                if remaining_quantity <= 0.0:
                    continue

                reserve_quantity = min(quantity, remaining_quantity)

                reservation = cls.get_reservation(source, destination,
                    reserve_quantity, destination.product.default_uom)
                consumed_quantities[key] = (consumed_quantity +
                    reserve_quantity)
                to_create.append(reservation._save_values)
                quantity -= reserve_quantity
                if quantity <= 0.0:
                    break

            if quantity <= 0.0:
                continue

            # Create reservation from purchase_lines
            for purchase_line in purchase_lines:
                purchase_location = (
                    purchase_line.purchase.warehouse.storage_location
                    if purchase_line.purchase.warehouse
                    else default_warehouse_location)
                if (purchase_line.product != destination.product
                        or not purchase_location
                        or purchase_location != destination.from_location):
                    continue
                key = ('purchase_line', purchase_line.id,)
                consumed_quantity = consumed_quantities.get(key, 0.0)
                internal_quantity = Uom.compute_qty(
                    purchase_line.unit, purchase_line.quantity,
                    purchase_line.product.default_uom)
                skip_ids = set(x.id for x in purchase_line.moves_recreated
                    + purchase_line.moves_ignored)
                for move in purchase_line.moves:
                    if move.state == 'done' and not move.id in skip_ids:
                        internal_quantity -= move.internal_quantity
                remaining_quantity = internal_quantity - consumed_quantity

                if remaining_quantity <= 0.0:
                    continue

                reserve_quantity = min(quantity, remaining_quantity)

                reservation = cls.get_reservation(None, destination,
                    reserve_quantity, destination.product.default_uom)
                reservation.source_document = purchase_line
                consumed_quantities[key] = (consumed_quantity +
                    reserve_quantity)
                to_create.append(reservation._save_values)
                quantity -= reserve_quantity
                if quantity <= 0.0:
                    break

            if quantity <= 0.0:
                continue

            # Create reservation from purchase_requests
            for purchase_request in requests:
                purchase_location = (
                    purchase_request.warehouse.storage_location
                    if purchase_request.warehouse
                    else default_warehouse_location)
                if (purchase_request.product != destination.product
                        or not purchase_location
                        or purchase_location != destination.from_location):
                    continue
                key = ('purchase_request', purchase_request.id,)
                consumed_quantity = consumed_quantities.get(key, 0.0)
                internal_quantity = Uom.compute_qty(
                    purchase_request.uom, purchase_request.quantity,
                    purchase_request.product.default_uom)
                remaining_quantity = internal_quantity - consumed_quantity

                if remaining_quantity <= 0.0:
                    continue

                reserve_quantity = min(quantity, remaining_quantity)

                reservation = cls.get_reservation(None, destination,
                    reserve_quantity, destination.product.default_uom)
                reservation.source_document = purchase_request
                consumed_quantities[key] = (consumed_quantity +
                    reserve_quantity)
                to_create.append(reservation._save_values)
                quantity -= reserve_quantity
                if quantity <= 0.0:
                    break

            if quantity <= 0.0:
                continue

            # Create reservation for remaining quantity in destination.
            reservation = cls.get_reservation(None, destination,
                quantity, destination.product.default_uom)
            to_create.append(reservation._save_values)

        # Create reservation for *remaining* quantities in source!!
        # That is:
        # * Source stock moves
        for source in cls.get_source_moves():
            key = ('source', source.id,)
            consumed_quantity = consumed_quantities.get(key, 0.0)
            remaining_quantity = (source.internal_quantity -
                consumed_quantity)

            if remaining_quantity <= 0.0:
                continue

            reservation = cls.get_reservation(source, None,
                remaining_quantity, source.product.default_uom)
            to_create.append(reservation._save_values)

        # * Purchase lines
        for purchase_line in purchase_lines:
            purchase_location = (
                purchase_line.purchase.warehouse.storage_location
                if purchase_line.purchase.warehouse
                else default_warehouse_location)
            if not purchase_location:
                continue

            key = ('purchase_line', purchase_line.id,)
            consumed_quantity = consumed_quantities.get(key, 0.0)
            internal_quantity = Uom.compute_qty(
                purchase_line.unit, purchase_line.quantity,
                purchase_line.product.default_uom)
            skip_ids = set(x.id for x in purchase_line.moves_recreated
                + purchase_line.moves_ignored)
            for move in purchase_line.moves:
                if move.state == 'done' and not move.id in skip_ids:
                    internal_quantity -= move.internal_quantity
            remaining_quantity = internal_quantity - consumed_quantity

            if remaining_quantity <= 0.0:
                continue

            reservation = cls(product=purchase_line.product,
                quantity=remaining_quantity,
                uom=purchase_line.unit,
                location=purchase_location,
                source_document=purchase_line)
            to_create.append(reservation._save_values)

        # * Purchase requests
        for purchase_request in requests:
            purchase_location = (
                purchase_request.warehouse.storage_location
                if purchase_request.warehouse
                else default_warehouse_location)
            if not purchase_location:
                continue

            key = ('purchase_request', purchase_request.id,)
            consumed_quantity = consumed_quantities.get(key, 0.0)
            internal_quantity = Uom.compute_qty(
                purchase_request.uom, purchase_request.quantity,
                purchase_request.product.default_uom)
            remaining_quantity = internal_quantity - consumed_quantity

            if remaining_quantity <= 0.0:
                continue

            reservation = cls(product=purchase_request.product,
                quantity=remaining_quantity,
                uom=purchase_request.product.default_uom,
                location=purchase_location,
                source_document=purchase_request)
            to_create.append(reservation._save_values)

        if to_create:
            return cls.create(to_create)
        return []

    @classmethod
    def get_purchase_requests(cls):
        """
        Get all purchase requests elegible to stock reservations
        """
        pool = Pool()
        Request = pool.get('purchase.request')
        domain = [
            ('purchase_line', '=', None),
            ]
        if hasattr(Request, 'customer'):
            domain.append(('customer', '=', None))
        return Request.search(domain, order=[
                ('purchase_date', 'ASC'),
                ])

    @classmethod
    def get_purchase_lines(cls):
        """
        Get all purchase lines elegible to stock reservations
        """
        pool = Pool()
        PurchaseLine = pool.get('purchase.line')
        # Must process confirmed purchases first because we want them to be
        # assigned before the ones in quotation or draft state
        confirmed_domain = [
            ('purchase.state', '=', ['confirmed']),
            ('product.type', '=', 'goods'),
            ('product.consumable', '=', False),
            ]
        if hasattr(Purchase, 'customer'):
            confirmed_domain.append(('purchase.customer', '=', None))
        confirmed = PurchaseLine.search(confirmed_domain, order=[
                ('purchase_date', 'ASC'),
                ])

        lines = []
        for line in confirmed:
            # TODO: Check if line is partialy delivered.
            if any(move.state == 'draft'for move in line.moves):
                lines.append(line)

        draft_quotation_domain = [
            ('purchase.state', 'in', ['draft', 'quotation']),
            ('product.type', '=', 'goods'),
            ('product.consumable', '=', False),
            ]
        if hasattr(Purchase, 'customer'):
            draft_quotation_domain.append(('purchase.customer', '=', None))
        lines += PurchaseLine.search(draft_quotation_domain, order=[
                ('purchase_date', 'ASC'),
                ])
        return lines

    @classmethod
    def get_destination_moves(cls):
        """
        Returns possible destination moves to create stock reservations
        """
        pool = Pool()
        Move = pool.get('stock.move')
        return Move.search([
                ('state', '=', 'draft'),
                ('from_location.type', 'in', ['storage']),
                ('to_location.type', 'in', ['storage', 'production']),
                # TODO: ('product.consumable', '=', False),
                ('product.template.type', '!=', 'service'),
                ['OR',
                    ('shipment', '=', None),
                    ('shipment', 'not like', 'stock.shipment.drop,%'),
                    ]
                ], order=[
                ('planned_date', 'ASC'),
                ('create_date', 'ASC'),
                ])

    @classmethod
    def get_source_moves(cls, move=None):
        """
        Returns matching source moves for a given destination move
        If move is None returns all elegible source moves
        """
        pool = Pool()
        Move = pool.get('stock.move')
        domain = [
            ('state', '=', 'draft'),
            ('product.template.type', '!=', 'service'),
            ('product.template.consumable', '=', False),
            ]
        if move:
            domain.extend([
                    ('product', '=', move.product),
                    ('to_location', '=', move.from_location),
                    ])
        else:
            domain.extend([
                    ('to_location.type', 'in', ['storage', 'production']),
                    # TODO: ('product.consumable', '=', False),
                    ('shipment', 'not like', 'stock.shipment.out,%'),
                    ('shipment', 'not like', 'stock.shipment.in.return,%'),
                    ('shipment', 'not like', 'stock.shipment.drop,%'),
                    ])
        return Move.search(domain, order=[
                ('planned_date', 'ASC'),
                ('internal_quantity', 'DESC'),
                ])

    @classmethod
    def get_reservation(cls, source, destination, quantity=None,
            uom=None):
        """
        Return the reservation to create given an source and destination move.
        The quantity param limits the reservation quantity
        The uom param is used to force the reservation uom
        """
        pool = Pool()
        Uom = pool.get('product.uom')
        ShipmentOut = pool.get('stock.shipment.out')
        move_uom = destination.uom if destination else source.uom
        if not quantity:
            quantity = destination.quantity
        if uom:
            quantity = Uom.compute_qty(move_uom, quantity, uom)
            move_uom = uom

        if destination:
            location = destination.from_location
            product = destination.product
        else:
            location = source.to_location
            product = source.product

        source_document = None
        if source:
            if source.shipment and not isinstance(source.shipment,
                    ShipmentOut):
                source_document = source.shipment
            elif source.production_output:
                source_document = source.production_output
            elif source.origin:
                source_document = source.origin
        return cls(source_document=source_document, source=source,
            destination=destination,
            product=product, quantity=quantity,
            uom=move_uom, location=location)


class WaitReservationStart(ModelView):
    'Wait Reservations'
    __name__ = 'stock.wait_reservation.start'


class WaitReservation(Wizard):
    'Return Sale'
    __name__ = 'stock.wait_reservation'
    start = StateView('stock.wait_reservation.start',
        'stock_reservation.wait_reservation_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Wait', 'wait_', 'tryton-ok', default=True),
            ])
    wait_ = StateTransition()

    def transition_wait_(self):
        Reservation = Pool().get('stock.reservation')

        reservations = Reservation.browse(Transaction().context['active_ids'])
        Reservation.wait(reservations)

        return 'end'


class CreateReservationsStart(ModelView):
    'Create Reservations'
    __name__ = 'stock.create_reservations.start'

    wait = fields.Boolean('Mark new reservations as waiting', help='If marked '
        'the new reservations will be created in waiting state.')

    @staticmethod
    def default_wait():
        return False


class CreateReservations(Wizard):
    'Create Reservations'
    __name__ = 'stock.create_reservations'
    start = StateView('stock.create_reservations.start',
        'stock_reservation.create_reservations_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create', 'create_', 'tryton-ok', default=True),
            ])
    create_ = StateAction('stock_reservation.act_stock_reservation_type')

    def do_create_(self, action):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        reservations = Reservation.generate_reservations()
        if self.start.wait:
            Reservation.wait([r for r in reservations
                    if r.reserve_type in ('on_time', 'in_stock', 'delayed')])
        return action, {}

    def transition_create_(self):
        return 'end'


class PrintReservationGraphStart(ModelView):
    'Print Reserve Graph'
    __name__ = 'stock.reservation.print_graph.start'
    level = fields.Integer('Level', required=True)

    @staticmethod
    def default_level():
        return 1


class PrintReservationGraph(Wizard):
    __name__ = 'stock.reservation.print_graph'

    start = StateView('stock.reservation.print_graph.start',
        'stock_reservation.print_reservation_graph_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
            ])
    print_ = StateAction('stock_reservation.report_reservation_graph')

    def transition_print_(self):
        return 'end'

    def do_print_(self, action):
        return action, {
            'id': Transaction().context.get('active_id'),
            'ids': Transaction().context.get('active_ids'),
            'level': self.start.level,
            }


class ReservationGraph(Report):
    __name__ = 'stock.reservation.graph'

    @classmethod
    def execute(cls, ids, data):
        import pydot
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        ActionReport = pool.get('ir.action.report')

        action_report_ids = ActionReport.search([
            ('report_name', '=', cls.__name__)
            ])
        if not action_report_ids:
            raise Exception('Error', 'Report (%s) not find!' % cls.__name__)
        action_report = ActionReport(action_report_ids[0])

        reserves = Reservation.browse(ids)

        graph = pydot.Dot(fontsize="8")
        graph.set('center', '1')
        graph.set('ratio', 'auto')
        cls.fill_graph(reserves, graph, level=data['level'])
        data = graph.create(prog='dot', format='png')
        return ('png', buffer(data), False, action_report.name)

    @classmethod
    def fill_graph(cls, reservations, graph, level=1, edges_data=None):
        '''
        Fills a pydot graph with a reserves.
        '''
        import pydot
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        if not edges_data:
            edges_data = {}

        if level > 0:
            sources = set()
            destinations = set()
            for reservation in reservations:
                if reservation.source:
                    move = reservation.source
                    sources.add(move)
                    edges_data[move] = reservation
                    if move.production_output:
                        for input in move.production_output.inputs:
                            sources.add(input)
                            edges_data[input] = reservation
                if reservation.destination:
                    move = reservation.destination
                    destinations.add(move)
                    edges_data[move] = reservation
                    if move.production_input:
                        for output in move.production_input.outputs:
                            sources.add(output)
                            edges_data[output] = reservation
            sub_reserves = Reservation.search([
                    ['OR',
                        ('source', 'in', list(sources)),
                        ('destination', 'in', list(destinations)),
                        ],
                    ])
            if sub_reserves:
                cls.fill_graph(sub_reserves, graph, level - 1, edges_data)

        for reserve in reservations:
            label = '"{' + reserve.rec_name + '\\n'
            #    label += '|'
            # TODO: Determine which info to show on lables.
#            label += reserve.reserve_type
#            label += '\l'
#            if reserve.source_document:
#                label += reserve.source_document.rec_name
#                label += '\l'
#            if reserve.destination_document:
#                label += reserve.destination_document.rec_name
#                label += '\l'
            label += '}"'
            node_name = str(reserve.id)
            node = pydot.Node(node_name, shape='record', label=label)
            graph.add_node(node)

            if reserve.source in edges_data:
                edge = pydot.Edge(
                    str(edges_data[reserve.source].id),
                    str(reserve.id),
                    )
                graph.add_edge(edge)

            if reserve.destination in edges_data:
                edge = pydot.Edge(
                    str(edges_data[reserve.destination].id),
                    str(reserve.id),
                    )
                graph.add_edge(edge)


class Move:
    __name__ = 'stock.move'

    reserves_source = fields.One2Many('stock.reservation', 'source',
        'Source Reserves')
    reserves_destination = fields.One2Many('stock.reservation', 'destination',
        'Destination Reserves')
    reserved_quantity = fields.Function(fields.Float('Reserved Quantity',
            digits=(16, Eval('unit_digits', 2)), depends=['unit_digits']),
        'get_reserved_quantity')
    future_reserved_quantity = fields.Function(fields.Float(
            'Future Reserved Quantity', digits=(16, Eval('unit_digits', 2)),
            depends=['unit_digits']), 'get_future_reserved_quantity')
    incompatible_reserved_quantity = fields.Function(fields.Float(
            'Incompatible Reserved Quantity', digits=(16,
                Eval('unit_digits', 2)), depends=['unit_digits']),
        'get_incompatible_reserved_quantity')

    @classmethod
    def __setup__(cls):
        super(Move, cls).__setup__()
        cls._error_messages.update({
            'write_reserved_move': 'The stock moves have related reserves and'
                ' they will be deleted.',
            'delete_reserved_move': 'The stock moves have related reserves and'
                ' they will be also deleted.',
            })
        cls.reserve_non_writable_fields = ('quantity', 'from_location',
                        'to_location')

    def get_reserved_quantity(self, name):
        if not self.reserves_destination:
            return self.internal_quantity
        quantity = 0.0
        for reservation in self.reserves_destination:
            if (reservation.state in ('confirmed', 'waiting')
                    and reservation.reserve_type == 'in_stock'):
                quantity += reservation.internal_quantity
        return quantity

    def get_future_reserved_quantity(self, name):
        quantity = 0.0
        for reservation in self.reserves_destination:
            if (reservation.state in ('confirmed', 'waiting')
                    and reservation.reserve_type in (
                        'delayed', 'on_time')):
                quantity += reservation.internal_quantity
        return quantity

    def get_incompatible_reserved_quantity(self, name):
        quantity = 0.0
        reservations = Reservation.search([
                ('location', '=', self.from_location.id),
                ('product', '=', self.product.id),
                ('destination', '=', self.id),
                ('state', 'in', ('waiting', 'confirmed')),
                ])
        for reservation in reservations:
            quantity += reservation.internal_quantity
        return quantity

    def pick_product(self, location_quantities):
        """
        Implementation without partial stock assignment
        """
        res = super(Move, self).pick_product(location_quantities)
        if not res:
            return res
        if self.reserved_quantity >= self.internal_quantity:
            return res
        if self.future_reserved_quantity:
            return []
        remaining = self.internal_quantity - self.reserved_quantity
        available = sum([x for x in location_quantities.itervalues()])
        if available - self.incompatible_reserved_quantity < remaining:
            return []
        return res

    @classmethod
    def draft(cls, moves):
        """
        When a move is moved to draft from assigned, its reservations are also
        moved to draft
        """
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        super(Move, cls).draft(moves)

        move_ids = [m.id for m in moves]
        reservations = Reservation.search([
                ('state', '=', 'done'),
                ('destination', 'in', move_ids),
                ])
        if reservations:
            Reservation.draft(reservations)

    @classmethod
    def assign(cls, moves):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        super(Move, cls).assign(moves)

        move_ids = [m.id for m in moves]
        reservations = Reservation.search([
                ('state', '=', 'waiting'),
                ('destination', 'in', move_ids),
                ])
        if reservations:
            Reservation.do(reservations)
        reservations = Reservation.search([
                ('state', '=', 'draft'),
                ('destination', 'in', move_ids),
                ])
        if reservations:
            Reservation.delete(reservations)

    @classmethod
    def do(cls, moves):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        super(Move, cls).do(moves)

        move_ids = [m.id for m in moves]
        reservations = Reservation.search([
                ('state', 'in', ['draft', 'waiting']),
                ('source', 'in', move_ids),
                ])
        if reservations:
            Reservation.write(reservations, {
                    'get_from_stock': True,
                    'source': None,
                    'source_document': None,
                    })

        reservations = Reservation.search([
                ('state', '=', 'draft'),
                ('source', 'in', move_ids),
                ])
        if reservations:
            Reservation.delete(reservations)

    @classmethod
    def cancel(cls, moves):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        super(Move, cls).cancel(moves)

        source_reservations = Reservation.search([
                ('state', '=', 'waiting'),
                ('source', 'in', [m.id for m in moves]),
                ])
        if source_reservations:
            Reservation.write(source_reservations, {
                    'failed_reason': 'source_canceled',
                    'failed_date': datetime.now(),
                    })
        destination_reservations = Reservation.search([
                ('state', '=', 'waiting'),
                ('destination', 'in', [m.id for m in moves]),
                ])
        if destination_reservations:
            Reservation.write(destination_reservations, {
                    'failed_reason': 'destination_canceled',
                    'failed_date': datetime.now(),
                    })
        Reservation.fail(source_reservations + destination_reservations)

    @classmethod
    def write(cls, *args):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        actions = iter(args)
        for moves, values in zip(actions, actions):
            non_writable_fields = list(set(cls.reserve_non_writable_fields)
                & set(values.keys()))
            if not non_writable_fields:
                continue

            invalid_write_moves = []
            for move in moves:
                for field in non_writable_fields:
                    current_value = getattr(move, field)
                    if isinstance(current_value, Model):
                        current_value = current_value.id
                    if current_value != values[field]:
                        invalid_write_moves.append(move)
                        break
            if invalid_write_moves:
                reserves = Reservation.search([
                            ['OR',
                                ('source', 'in', invalid_write_moves),
                                ('destination', 'in', invalid_write_moves),
                                ]
                            ])
                if reserves:
                    moves_id = ','.join(str(m) for m in moves)
                    cls.raise_user_warning('%s.write' % moves_id,
                        'write_reserved_move')
                    Reservation.delete(reserves)
        super(Move, cls).write(*args)

    @classmethod
    def delete(cls, moves):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        if Reservation.search([
                    ['OR',
                        ('source', 'in', moves),
                        ('destination', 'in', moves),
                        ]
                    ]):
            moves_id = ','.join(str(m) for m in moves)
            cls.raise_user_warning('%s.delete' % moves_id,
                'delete_reserved_move')
        super(Move, cls).delete(moves)


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


class ReserveRelatedMixin:

    reserves = fields.Function(fields.One2Many('stock.reservation', None,
            'Reserves'), 'get_reserves')
    reserve_state = fields.Function(fields.Selection([
                ('none', 'None'),
                ('pending', 'Pending'),
                ('delayed', 'Delayed'),
                ('on_time', 'On Time'),
                ], 'Reserve State'), 'get_reserve_state',
        searcher='search_reserve_state')
    reserve_day_difference = fields.Function(fields.Integer('Day Difference'),
        'get_reserve_day_difference',
        searcher='search_reserve_day_difference')

    def get_reserves(self, name):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        return [x.id for x in Reservation.search([
                    ('destination_document', '=', str(self))])]

    def get_reserve_state(self, name):
        if not self.reserves:
            return 'none'
        if any(x.reserve_type == 'pending' for x in self.reserves):
            return 'pending'
        if any(x.reserve_type == 'delayed' for x in self.reserves):
            return 'delayed'
        if all((x.reserve_type == 'on_time' or x.reserve_type == 'in_stock')
                for x in self.reserves):
            return 'on_time'
        return 'none'

    def get_reserve_day_difference(self, name):
        reserves_difference = [x.day_difference for x in self.reserves
            if x.day_difference]
        if not reserves_difference:
            return
        return max(reserves_difference)

    @classmethod
    def search_reserve_state(cls, name, clause):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        clause[0] = 'reserve_type'
        if clause[2] == 'on_time':
            clause[1] = 'in' if clause[1] == '=' else 'not in'
            clause[2] = ['on_time', 'in_stock']
        reserves = Reservation.search([
                ('destination_document', 'like', cls.__name__ + ',%'),
                clause,
                ])
        return [('id', 'in', [x.destination_document.id for x in reserves])]

    @classmethod
    def search_reserve_day_difference(cls, name, clause):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        clause[0] = 'day_difference'
        reserves = Reservation.search([
                ('destination_document', 'like', cls.__name__ + ',%'),
                clause,
                ])
        return [('id', 'in', [x.destination_document.id for x in reserves])]


class Production(ReserveRelatedMixin):
    __name__ = 'production'

    ready_to_assign = fields.Function(fields.Boolean('Ready to assign'),
        'get_ready_to_assign', searcher='search_ready_to_assign')

    @classmethod
    def get_ready_to_assign(cls, productions, name):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        productions_inputs = {}
        for production in productions:
            product_quantities = {}
            for input in production.inputs:
                qty = product_quantities.setdefault(input.product, 0.0)
                product_quantities[input.product] = (qty +
                    input.internal_quantity)
            productions_inputs[production] = product_quantities

        reserves = Reservation.search([
                ('destination', 'in',
                    [m for p in productions for m in p.inputs]),
                ])
        for reserve in reserves:
            if (not reserve.destination and not
                    reserve.destination.production_input):
                # It shouldn't happen
                continue
            if reserve.reserve_type == 'in_stock':
                production = reserve.destination.production_input
                qty = productions_inputs[production].get(reserve.product, None)
                if qty is None:
                    # already removed
                    continue
                qty -= reserve.internal_quantity
                if qty <= reserve.uom.rounding:
                    del productions_inputs[production][reserve.product]
                else:
                    productions_inputs[production][reserve.product] = qty

        res = {}
        for production, value in productions_inputs.iteritems():
            res[production.id] = not bool(value)
        return res

    @classmethod
    def search_ready_to_assign(cls, name, clause):
        # TODO: apply changes done in get_ready_to_assign
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        reserves = Reservation.search([
                ('reserve_type', '=', 'in_stock'),
                ])

        productions_inputs = {}
        productions = set()
        for reserve in reserves:
            production = (reserve.destination and
                reserve.destination.production_input)
            if not production:
                continue
            if not production in productions_inputs:
                product_quantities = {}
                for input in production.inputs:
                    qty = product_quantities.setdefault(input.product, 0.0)
                    product_quantities[input.product] = (qty +
                        input.internal_quantity)
                productions_inputs[production] = product_quantities
            product_quantities = productions_inputs[production]
            qty = product_quantities.setdefault(reserve.product, 0.0)
            qty -= reserve.internal_quantity
            if qty <= 0.0:
                del product_quantities[reserve.product]
            else:
                product_quantities[reserve.product] = qty
            if not product_quantities:
                productions.add(production)
            productions_inputs[production] = product_quantities

        operator = 'in' if clause[2] else 'not in'
        return [('id', operator, [x.id for x in productions])]

    @classmethod
    def delete(cls, productions):
        delete_related_reservations(productions, 'source_document')
        super(Production, cls).delete(productions)


class Sale(ReserveRelatedMixin):
    __name__ = 'sale.sale'

    purchases = fields.Function(fields.One2Many('purchase.purchase', None,
            'Purchases'), 'get_purchases', searcher='search_purchases')

    purchase_requests = fields.Function(fields.One2Many('purchase.request',
            None, 'Purchase Requests'), 'get_purchase_requests',
        searcher='search_purchase_requests')

    def get_recursive_reservations(self):
        pool = Pool()
        Move = pool.get('stock.move')
        Reservation = pool.get('stock.reservation')

        def get_recursive_moves(moves, processed_moves=None):
            if not moves:
                return []
            if processed_moves is None:
                processed_moves = set()

            reservations = Reservation.search([
                    ('destination', 'in', moves),
                    ])
            new_moves = set([r.source for r in reservations
                    if r.source and isinstance(r.source, Move)])
            for move in moves:
                if move.id in processed_moves:
                    continue
                if move.production_output:
                    new_moves |= set(move.production_output.inputs)
                processed_moves.add(move.id)

            reservations += get_recursive_moves(list(new_moves),
                processed_moves)

            return reservations

        moves = []
        for shipment in self.shipments + self.shipment_returns:
            moves += shipment.inventory_moves
        return get_recursive_moves(moves)

    def get_purchases(self, name):
        pool = Pool()
        PurchaseLine = pool.get('purchase.line')
        SaleLine = pool.get('sale.line')

        purchases = set()
        for reservation in self.get_recursive_reservations():
            if reservation.source and reservation.source.origin:
                origin = reservation.source.origin
                if isinstance(origin, PurchaseLine):
                    purchases.add(origin.purchase)
            elif reservation.source_document and isinstance(
                    reservation.source_document, PurchaseLine):
                purchases.add(reservation.source_document.purchase)
        # support sale_supply(_drop_shipment)
        if hasattr(SaleLine, 'purchase_request'):
            for line in self.lines:
                if line.purchase_request and line.purchase_request.purchase:
                    purchases.add(line.purchase_request.purchase)
        return [p.id for p in purchases]

    @classmethod
    def search_purchases(cls, name, clause):
        pool = Pool()
        Purchase = pool.get('purchase.purchase')
        sales = set()
        for purchase in Purchase.search([('id',) + tuple(clause[1:])]):
            for sale in purchase.sales:
                sales.add(sale.id)
        return [('id', 'in', sales)]

    def get_purchase_requests(self, name):
        pool = Pool()
        Request = pool.get('purchase.request')
        SaleLine = pool.get('sale.line')

        requests = set()
        for reservation in self.get_recursive_reservations():
            if reservation.source_document and isinstance(
                    reservation.source_document, Request):
                requests.add(reservation.source_document)
        # support sale_supply(_drop_shipment)
        if hasattr(SaleLine, 'purchase_request'):
            for line in self.lines:
                if line.purchase_request:
                    requests.add(line.purchase_request)
        return [r.id for r in requests]

    @classmethod
    def search_purchase_requests(cls, name, clause):
        pool = Pool()
        Request = pool.get('purchase.request')
        sales = set()
        for request in Request.search([('id',) + tuple(clause[1:])]):
            for sale in request.sales:
                sales.add(sale.id)
        return [('id', 'in', sales)]


class ShipmentOut(ReserveRelatedMixin):
    __name__ = 'stock.shipment.out'

    ready_to_assign = fields.Function(fields.Boolean('Ready to assign'),
        'get_ready_to_assign', searcher='search_ready_to_assign')

    @classmethod
    def get_ready_to_assign(cls, shipments, name):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        inventory_moves = [m for s in shipments for m in s.inventory_moves]
        reserves = Reservation.search([
                ('destination', 'in', inventory_moves)
                ])

        reserves_by_shipment = {}
        for reserve in reserves:
            reserves_by_shipment.setdefault(reserve.destination.shipment.id,
                []).append(bool(reserve.reserve_type == 'in_stock'))

        res = {}
        for shipment in shipments:
            res[shipment.id] = (all(reserves_by_shipment[shipment.id])
                if shipment.id in reserves_by_shipment else False)
        return res

    @classmethod
    def search_ready_to_assign(cls, name, clause):
        pool = Pool()
        Reservation = pool.get('stock.reservation')

        reserves = Reservation.search([
                ('reserve_type', '=', 'in_stock'),
                ])

        shipments = set()
        for reserve in reserves:
            shipment = reserve.destination_document or (reserve.destination
                and reserve.destination.shipment)
            if isinstance(shipment, cls):
                shipments.add(shipment)

        operator = 'in' if clause[2] else 'not in'
        return [('id', operator, [x.id for x in shipments])]


class ShipmentOutReturn:
    __name__ = 'stock.shipment.out.return'

    @classmethod
    def delete(cls, shipments):
        delete_related_reservations(shipments, 'source_document')
        super(ShipmentOutReturn, cls).delete(shipments)


class ShipmentIn:
    __name__ = 'stock.shipment.in'

    @classmethod
    def create_inventory_moves(cls, shipments):
        pool = Pool()
        Reservation = pool.get('stock.reservation')
        super(ShipmentIn, cls).create_inventory_moves(shipments)
        for shipment in shipments:
            for inventory_move in shipment.inventory_moves:
                for incoming_move in shipment.incoming_moves:
                    if (inventory_move.product == incoming_move.product and
                            (inventory_move.internal_quantity ==
                                incoming_move.internal_quantity)):
                            if isinstance(incoming_move.origin, PurchaseLine):
                                reserves = Reservation.search([
                                        ('state', 'in', ['draft', 'waiting']),
                                        ('source_document', '=',
                                            str(incoming_move.origin)),
                                        ])
                                if reserves:
                                    Reservation.write(reserves, {
                                            'source': inventory_move.id,
                                            })
                            break

    @classmethod
    def delete(cls, shipments):
        delete_related_reservations(shipments, 'source_document')
        super(ShipmentIn, cls).delete(shipments)


class ShipmentInternal:
    __name__ = 'stock.shipment.internal'

    @classmethod
    def delete(cls, shipments):
        delete_related_reservations(shipments, 'source_document')
        super(ShipmentInternal, cls).delete(shipments)


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
                elif reservation.destination_document:
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
        reservations = Reservation.search([
                ('source_document', '=', str(self)),
                ])

        for reservation in reservations:
            if reservation.destination:
                if reservation.destination.origin:
                    origin = reservation.destination.origin
                    if isinstance(origin, SaleLine):
                        sales.add(origin.sale)
                elif reservation.destination_document:
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
