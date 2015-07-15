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
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install stock_reservation Module::

    >>> Module = Model.get('ir.module.module')
    >>> modules = Module.find([('name', '=', 'stock_reservation')])
    >>> Module.install([x.id for x in modules], config.context)
    >>> Wizard('ir.module.module.install_upgrade').execute('upgrade')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> CurrencyRate = Model.get('currency.currency.rate')
    >>> Company = Model.get('company.company')
    >>> Party = Model.get('party.party')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> party = Party(name='Dunder Mifflin')
    >>> party.save()
    >>> company.party = party
    >>> currencies = Currency.find([('code', '=', 'USD')])
    >>> if not currencies:
    ...     currency = Currency(name='US Dollar', symbol='$', code='USD',
    ...     rounding=Decimal('0.01'), mon_grouping='[3, 3, 0]',
    ...     mon_decimal_point='.')
    ...     currency.save()
    ...     CurrencyRate(date=today + relativedelta(month=1, day=1),
    ...     rate=Decimal('1.0'), currency=currency).save()
    ... else:
    ...     currency, = currencies
    >>> company.currency = currency
    >>> company_config.execute('add')
    >>> company, = Company.find()

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> FiscalYear = Model.get('account.fiscalyear')
    >>> Sequence = Model.get('ir.sequence')
    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> fiscalyear = FiscalYear(name=str(today.year))
    >>> fiscalyear.start_date = today + relativedelta(month=1, day=1)
    >>> fiscalyear.end_date = today + relativedelta(month=12, day=31)
    >>> fiscalyear.company = company
    >>> post_move_seq = Sequence(name=str(today.year), code='account.move',
    ...      company=company)
    >>> post_move_seq.save()
    >>> fiscalyear.post_move_sequence = post_move_seq
    >>> invoice_seq = SequenceStrict(name=str(today.year),
    ...      code='account.invoice', company=company)
    >>> invoice_seq.save()
    >>> fiscalyear.out_invoice_sequence = invoice_seq
    >>> fiscalyear.in_invoice_sequence = invoice_seq
    >>> fiscalyear.out_credit_note_sequence = invoice_seq
    >>> fiscalyear.in_credit_note_sequence = invoice_seq
    >>> fiscalyear.save()
    >>> FiscalYear.create_period([fiscalyear.id], config.context)

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> account_template, = AccountTemplate.find([('parent', '=', None)])
    >>> create_chart = Wizard('account.create_chart')
    >>> create_chart.execute('account')
    >>> create_chart.form.account_template = account_template
    >>> create_chart.form.company = company
    >>> create_chart.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('kind', '=', 'receivable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> payable, = Account.find([
    ...         ('kind', '=', 'payable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> revenue, = Account.find([
    ...         ('kind', '=', 'revenue'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> expense, = Account.find([
    ...         ('kind', '=', 'expense'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> account_tax, = Account.find([
    ...         ('kind', '=', 'other'),
    ...         ('company', '=', company.id),
    ...         ('name', '=', 'Main Tax'),
    ...         ])
    >>> create_chart.form.account_receivable = receivable
    >>> create_chart.form.account_payable = payable
    >>> create_chart.execute('create_properties')

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> PaymentTermLine = Model.get('account.invoice.payment_term.line')
    >>> payment_term = PaymentTerm(name='Direct')
    >>> payment_term_line = PaymentTermLine(type='remainder', days=0)
    >>> payment_term.lines.append(payment_term_line)
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

Make a reservation::

    >>> StockMove = Model.get('stock.move')
    >>> StockReservation = Model.get('stock.reservation')
    >>> incoming_move = StockMove()
    >>> incoming_move.product = product
    >>> incoming_move.uom = unit
    >>> incoming_move.quantity = 1
    >>> incoming_move.from_location = input_loc
    >>> incoming_move.to_location = storage_loc
    >>> incoming_move.planned_date = today
    >>> incoming_move.effective_date = today
    >>> incoming_move.company = company
    >>> incoming_move.unit_price = Decimal('100')
    >>> incoming_move.currency = currency
    >>> incoming_move.save()
    >>> outgoing_move = StockMove()
    >>> outgoing_move.product = product
    >>> outgoing_move.uom = unit
    >>> outgoing_move.quantity = 1
    >>> outgoing_move.from_location = storage_loc
    >>> outgoing_move.to_location = output_loc
    >>> outgoing_move.planned_date = today
    >>> outgoing_move.effective_date = today
    >>> outgoing_move.company = company
    >>> outgoing_move.unit_price = Decimal('100')
    >>> outgoing_move.currency = currency
    >>> outgoing_move.save()
    >>> reservation = StockReservation()
    >>> reservation.product = product
    >>> reservation.uom = unit
    >>> reservation.quantity = 1
    >>> reservation.location = storage_loc
    >>> reservation.destination = outgoing_move
    >>> reservation.source = incoming_move
    >>> reservation.save()
    >>> reservation.state == 'draft'
    True
    >>> incoming_move.state == 'draft'
    True
    >>> outgoing_move.state == 'draft'
    True

Wait the reservation::

    >>> StockReservation.wait([reservation.id], config.context)
    >>> reservation.reload()
    >>> reservation.state == 'waiting'
    True
    >>> incoming_move.reload()
    >>> incoming_move.reserved_quantity > 0
    True

Do the reserve::

    >>> StockMove.assign([incoming_move.id], config.context)
    >>> StockMove.do([incoming_move.id], config.context)
    >>> reservation.reload()
    >>> reservation.state
    u'waiting'
    >>> reservation.reserve_type == 'in_stock'
    True
    >>> outgoing_move.reload()
    >>> outgoing_move.state
    u'draft'
    >>> StockMove.assign([outgoing_move.id], config.context)
    >>> StockMove.do([outgoing_move.id], config.context)
    >>> outgoing_move.reload()
    >>> outgoing_move.state
    u'done'
    >>> reservation.reload()
    >>> reservation.state
    u'done'

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

    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state = 'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity == request.quantity
    True
    >>> reservation.source_document == request
    True
    >>> reservation.reserve_type == 'exceeding'
    True

Confirm purchase request and check reserve from purchase line::

    >>> PurchaseLine = Model.get('purchase.line')
    >>> request.party = supplier
    >>> request.save()
    >>> create_purchase = Wizard('purchase.request.create_purchase',
    ...     models=[request])
    >>> create_purchase.form.payment_term = payment_term
    >>> create_purchase.execute('start')
    >>> purchase_line, = PurchaseLine.find([])
    >>> purchase_line.quantity
    15.0
    >>> purchase_line.purchase.warehouse.storage_location == storage_loc
    True
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state = 'draft'
    >>> reservation.product == request.product
    True
    >>> reservation.quantity == request.quantity
    True
    >>> reservation.source_document == purchase_line
    True
    >>> reservation.reserve_type == 'exceeding'
    True

Create an Outgoing Shipment for 10 units and test assigned to purchase line::

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
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> reservation, exceding_reservation = reserves
    >>> reservation.state = 'draft'
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
    >>> reservation.reserve_type == 'on_time'
    True
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type == 'exceeding'
    True


Confirm the purchase and test reserve assigned to stock::

    >>> Purchase = Model.get('purchase.purchase')
    >>> purchase = purchase_line.purchase
    >>> purchase.purchase_date = today
    >>> purchase.save()
    >>> Purchase.quote([purchase.id], config.context)
    >>> Purchase.confirm([purchase.id], config.context)
    >>> purchase_move, = purchase.moves
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> reservation, exceding_reservation = reserves
    >>> reservation.state = 'draft'
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
    >>> reservation.reserve_type == 'on_time'
    True
    >>> shipment_out.reserve_state == 'on_time'
    True
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type == 'exceeding'
    True

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
    >>> reserves = StockReservation.find([('state', '=', 'draft')])
    >>> stock_reservation, _, reservation, exceding_reservation = reserves
    >>> stock_reservation.reserve_type == 'in_stock'
    True
    >>> stock_reservation.location == input_loc
    True
    >>> reservation.product == request.product
    True
    >>> reservation.quantity
    10.0
    >>> reservation.source_document == shipment_in
    True
    >>> shipment_in.reload()
    >>> shipment_in_move, = shipment_in.inventory_moves
    >>> reservation.source == shipment_in_move
    True
    >>> shipment_out_move, = shipment_out.inventory_moves
    >>> reservation.destination == shipment_out_move
    True
    >>> reservation.destination_document == shipment_out
    True
    >>> reservation.reserve_type == 'on_time'
    True
    >>> shipment_out.reserve_state == 'on_time'
    True
    >>> exceding_reservation.source_document == shipment_in
    True
    >>> exceding_reservation.quantity
    5.0
    >>> exceding_reservation.reserve_type == 'exceeding'
    True
