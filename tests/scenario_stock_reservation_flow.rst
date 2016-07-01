==========================
Stock Reservation Scenario
==========================

=============
General Setup
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax, set_tax_code
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install stock_reservation Module::

    >>> Module = Model.get('ir.module')
    >>> modules = Module.find([('name', '=', 'stock_reservation')])
    >>> Module.install([x.id for x in modules], config.context)
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Get currency::

    >>> currency = company.currency

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'Product'
    >>> template.default_uom = unit
    >>> template.type = 'goods'
    >>> template.purchasable = True
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.cost_price = Decimal('5')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Get stock locations::

    >>> Location = Model.get('stock.location')
    >>> warehouse_loc, = Location.find([('code', '=', 'WH')])
    >>> supplier_loc, = Location.find([('code', '=', 'SUP')])
    >>> storage_loc, = Location.find([('code', '=', 'STO')])
    >>> customer_loc, = Location.find([('code', '=', 'CUS')])
    >>> output_loc, = Location.find([('code', '=', 'OUT')])
    >>> input_loc, = Location.find([('code', '=', 'IN')])

Create purchase order point::

    >>> OrderPoint = Model.get('stock.order_point')
    >>> order_point = OrderPoint()
    >>> order_point.product = product
    >>> order_point.warehouse_location = warehouse_loc
    >>> order_point.type = 'purchase'
    >>> order_point.min_quantity = 10
    >>> order_point.max_quantity = 15
    >>> order_point.save()


Execute create purchase requests supply::

    >>> PurchaseRequest = Model.get('purchase.request')
    >>> Wizard('purchase.request.create').execute('create_')
    >>> request, = PurchaseRequest.find([])
    >>> request.state == 'draft'
    True
    >>> request.product.template.name == 'Product'
    True
    >>> request.quantity
    15.0

Create an Outgoing Shipment for 10 units::

    >>> StockMove = Model.get('stock.move')
    >>> ShipmentOut = Model.get('stock.shipment.out')
    >>> shipment_out = ShipmentOut()
    >>> shipment_out.planned_date = today
    >>> shipment_out.customer = customer
    >>> shipment_out.warehouse = warehouse_loc
    >>> shipment_out.company = company
    >>> move = StockMove()
    >>> shipment_out.outgoing_moves.append(move)
    >>> move.product = product
    >>> move.uom =unit
    >>> move.quantity = 10
    >>> move.from_location = output_loc
    >>> move.to_location = customer_loc
    >>> move.company = company
    >>> move.unit_price = Decimal('1')
    >>> move.currency = currency
    >>> shipment_out.save()
    >>> ShipmentOut.wait([shipment_out.id], config.context)
    >>> shipment_out.reload()
    >>> move, = shipment_out.inventory_moves
    >>> move.quantity
    10.0
    >>> move.state == 'draft'
    True
    >>> move.from_location == storage_loc
    True

Create reserve and check assigned from Request::

    >>> StockReservation = Model.get('stock.reservation')
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> reservation, exceding_reservation = reserves
    >>> reservation.state = 'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    10.0
    >>> reservation.source_document == request
    True
    >>> reservation.destination == move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type == 'on_time'
    True
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type == 'exceeding'
    True

Confirm purchase request and check reserve from purchase line::

    >>> PurchaseLine = Model.get('purchase.line')
    >>> request.party = supplier
    >>> request.save()
    >>> create_purchase = Wizard('purchase.request.create_purchase', [request])
    >>> purchase_line, = PurchaseLine.find([])
    >>> purchase_line.quantity
    15.0
    >>> purchase_line.purchase.warehouse.storage_location == storage_loc
    True
    >>> reservation.reload()
    >>> reservation.state = 'draft'
    >>> reservation.product == purchase_line.product
    True
    >>> reservation.quantity == move.quantity
    True
    >>> reservation.source_document == purchase_line
    True


Confirm the purchase and test reserve still assigned to line::

    >>> Purchase = Model.get('purchase.purchase')
    >>> purchase = purchase_line.purchase
    >>> purchase.purchase_date = today
    >>> purchase.payment_term = payment_term
    >>> purchase.save()
    >>> purchase.click('quote')
    >>> purchase.click('confirm')
    >>> purchase.click('process')
    >>> purchase_move, = purchase.moves
    >>> reservation.reload()
    >>> reservation.state = 'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    10.0
    >>> reservation.source == None
    True
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.destination == move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type == 'on_time'
    True

Recieve the purchase line and then the reserve should be related to the move::

    >>> ShipmentIn = Model.get('stock.shipment.in')
    >>> shipment = ShipmentIn()
    >>> shipment.supplier = supplier
    >>> supplier_move = StockMove(purchase_move.id)
    >>> shipment.incoming_moves.append(supplier_move)
    >>> shipment.save()
    >>> ShipmentIn.receive([shipment.id], config.context)
    >>> reservation.reload()
    >>> reservation.quantity
    10.0
    >>> inventory_move, = shipment.inventory_moves
    >>> reservation.source == inventory_move
    True
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.destination == move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type == 'on_time'
    True

Finish the shipment and reserve_type should be in_stock::

    >>> ShipmentIn.done([shipment.id], config.context)
    >>> reservation.reload()
    >>> reservation.reserve_type == 'in_stock'
    True
