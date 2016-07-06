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

Check reserve from purchase requests::

    >>> StockReservation = Model.get('stock.reservation')
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state
    u'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    15.0
    >>> reservation.source_document == request
    True
    >>> reservation.reserve_type
    'exceeding'

Confirm purchase request and check reserve from purchase line::

    >>> PurchaseLine = Model.get('purchase.line')
    >>> request.party = supplier
    >>> request.save()
    >>> create_p = Wizard('purchase.request.create_purchase', models=[request])
    >>> purchase_line, = PurchaseLine.find([])
    >>> purchase_line.quantity
    15.0
    >>> purchase_line.purchase.warehouse.storage_location == storage_loc
    True
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state
    u'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    15.0
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.reserve_type
    'exceeding'

Create an Outgoing Shipment for 10 units and test assigned to purchase line::

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
    >>> move.uom = unit
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
    >>> move.state
    u'draft'
    >>> move.from_location == storage_loc
    True
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> reservation, exceding_reservation = reserves
    >>> reservation.state
    u'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    10.0
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.destination == move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type
    'on_time'
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type
    'exceeding'

Confirm the purchase and test reserve assigned to stock::

    >>> Purchase = Model.get('purchase.purchase')
    >>> purchase = purchase_line.purchase
    >>> purchase.purchase_date = today
    >>> purchase.payment_term = payment_term
    >>> purchase.click('quote')
    >>> purchase.click('confirm')
    >>> purchase.click('process')
    >>> purchase_move, = purchase.moves
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> reservation, exceding_reservation = reserves
    >>> reservation.state
    u'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    10.0
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.destination == move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type
    'on_time'
    >>> shipment_out.reserve_state
    'on_time'
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type
    'exceeding'

Recieve the shipment and check reserve assigned to shipment::

    >>> ShipmentIn = Model.get('stock.shipment.in')
    >>> shipment_in = ShipmentIn()
    >>> shipment_in.supplier = supplier
    >>> for move in purchase.moves:
    ...     incoming_move = StockMove(id=move.id)
    ...     shipment_in.incoming_moves.append(incoming_move)
    >>> shipment_in.save()
    >>> ShipmentIn.receive([shipment_in.id], config.context)
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> re1, re2, re3 = reserves
    >>> re1.reserve_type == 'in_stock'
    True
    >>> re1.location == input_loc
    True
    >>> re1.product == request.product
    True
    >>> re1.quantity
    15.0
    >>> re2.reserve_type == 'on_time'
    True
    >>> re2.location == storage_loc
    True
    >>> re2.product == request.product
    True
    >>> re2.quantity
    10.0
    >>> re3.reserve_type == 'exceeding'
    True
    >>> re3.location == storage_loc
    True
    >>> re3.product == request.product
    True
    >>> re3.quantity
    5.0
