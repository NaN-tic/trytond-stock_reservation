=========================================
Stock Reservation Child Location Scenario
=========================================

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
    >>> payable = accounts['payable']
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
    >>> child_loc = Location(name='Child')
    >>> child_loc.parent = storage_loc
    >>> child_loc.save()

Create stock and a outgoing move::

    >>> StockMove = Model.get('stock.move')
    >>> incoming_move = StockMove()
    >>> incoming_move.product = product
    >>> incoming_move.uom = unit
    >>> incoming_move.quantity = 1
    >>> incoming_move.from_location = input_loc
    >>> incoming_move.to_location = child_loc
    >>> incoming_move.planned_date = today
    >>> incoming_move.effective_date = today
    >>> incoming_move.company = company
    >>> incoming_move.unit_price = Decimal('100')
    >>> incoming_move.currency = currency
    >>> incoming_move.click('do')
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

Check reserve from stock::

    >>> StockReservation = Model.get('stock.reservation')
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state
    u'draft'
    >>> reservation.destination == outgoing_move
    True
    >>> reservation.product == product
    True
    >>> reservation.location == storage_loc
    True
    >>> reservation.stock_location == child_loc
    True
    >>> reservation.quantity
    1.0
    >>> reservation.reserve_type
    'in_stock'

Check reserve from stock::

    >>> StockReservation = Model.get('stock.reservation')
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> reservation, = StockReservation.find([('state', '=', 'draft')])
    >>> reservation.state
    u'draft'
    >>> reservation.destination == outgoing_move
    True
    >>> reservation.product == product
    True
    >>> reservation.location == storage_loc
    True
    >>> reservation.stock_location == child_loc
    True
    >>> reservation.quantity
    1.0
    >>> reservation.reserve_type
    'in_stock'

Create more stock in parent and increase outgoing move quantity::

    >>> reservation.delete()
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
    >>> incoming_move.click('do')
    >>> outgoing_move.quantity = 2
    >>> outgoing_move.save()
    >>> create_reservations = Wizard('stock.create_reservations')
    >>> create_reservations.execute('create_')
    >>> child_res, parent_res = StockReservation.find([
    ...         ('state', '=', 'draft')])
    >>> child_res.state
    u'draft'
    >>> child_res.destination == outgoing_move
    True
    >>> child_res.product == product
    True
    >>> child_res.location == storage_loc
    True
    >>> child_res.stock_location == child_loc
    True
    >>> child_res.quantity
    1.0
    >>> child_res.reserve_type
    'in_stock'
    >>> parent_res.state
    u'draft'
    >>> parent_res.destination == outgoing_move
    True
    >>> parent_res.product == product
    True
    >>> parent_res.location == storage_loc
    True
    >>> parent_res.stock_location == storage_loc
    True
    >>> parent_res.quantity
    1.0
    >>> parent_res.reserve_type
    'in_stock'
