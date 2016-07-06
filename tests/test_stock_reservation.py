#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
import unittest
import doctest
import trytond.tests.test_tryton
from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import doctest_setup, doctest_teardown
from trytond.exceptions import UserWarning

from trytond.modules.company.tests import create_company, set_company


class StockReservationTestCase(ModuleTestCase):
    'Test Stock Reservation module'
    module = 'stock_reservation'

    @with_transaction()
    def test0010_reserved_warning(self):
        'Test a warning is raised when modifing a reserved move'
        pool = Pool()
        Template = pool.get('product.template')
        Product = pool.get('product.product')
        Uom = pool.get('product.uom')
        Location = pool.get('stock.location')
        Move = pool.get('stock.move')
        Reservation = pool.get('stock.reservation')

        kg, = Uom.search([('name', '=', 'Kilogram')])
        template, = Template.create([{
                    'name': 'Test Move.internal_quantity',
                    'type': 'goods',
                    'list_price': Decimal(1),
                    'cost_price': Decimal(0),
                    'cost_price_method': 'fixed',
                    'default_uom': kg.id,
                    }])
        product, = Product.create([{
                    'template': template.id,
                    }])
        supplier, = Location.search([('code', '=', 'SUP')])
        storage, = Location.search([('code', '=', 'STO')])
        output, = Location.search([('code', '=', 'OUT')])
        customer, = Location.search([('code', '=', 'CUS')])
        company = create_company()
        currency = company.currency
        with set_company(company):
            source, destination = Move.create([{
                        'product': product.id,
                        'uom': kg.id,
                        'quantity': 1.0,
                        'from_location': supplier.id,
                        'to_location': storage.id,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }, {
                        'product': product.id,
                        'uom': kg.id,
                        'quantity': 1.0,
                        'from_location': storage.id,
                        'to_location': output.id,
                        'company': company.id,
                        'unit_price': Decimal('1'),
                        'currency': currency.id,
                        }])
            reservation, = Reservation.create([{
                        'product': product.id,
                        'uom': kg.id,
                        'quantity': 1.0,
                        'location': storage.id,
                        'company': company.id,
                        'source': source.id,
                        'destination': destination.id,
                        }])
            for move in [source, destination]:
                self.assertRaises(UserWarning, Move.delete, [move])

            # Check that we can write to_unit_price
            Move.write([source, destination], {
                    'unit_price': Decimal('2.0'),
                    })
            for field, value in [
                    ('quantity', 2),
                    ('from_location', customer.id),
                    ('to_location', customer.id),
                    ]:
                for move in [source, destination]:
                    self.assertRaises(UserWarning, Move.write, [move], {
                            field: value,
                            })


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            StockReservationTestCase))
    suite.addTests(doctest.DocFileSuite('scenario_stock_reservation.rst',
            setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    suite.addTests(doctest.DocFileSuite('scenario_stock_reservation_flow.rst',
            setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    suite.addTests(doctest.DocFileSuite(
            'scenario_stock_reservation_child_locations.rst',
            setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite
