#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
import unittest
import doctest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.tests.test_tryton import test_view, test_depends
from trytond.tests.test_tryton import doctest_setup, doctest_teardown
from trytond.exceptions import UserWarning
from trytond.transaction import Transaction


class TestCase(unittest.TestCase):
    'Test module'

    def setUp(self):
        trytond.tests.test_tryton.install_module('stock_reservation')
        self.company = POOL.get('company.company')
        self.template = POOL.get('product.template')
        self.product = POOL.get('product.product')
        self.category = POOL.get('product.category')
        self.uom = POOL.get('product.uom')
        self.location = POOL.get('stock.location')
        self.move = POOL.get('stock.move')
        self.reservation = POOL.get('stock.reservation')
        self.user = POOL.get('res.user')

    def test0005views(self):
        'Test views'
        test_view('stock_reservation')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def test0010_reserved_warning(self):
        'Test a warning is raised when modifing a reserved move'
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            category, = self.category.create([{
                        'name': 'Test Move.internal_quantity',
                        }])
            kg, = self.uom.search([('name', '=', 'Kilogram')])
            template, = self.template.create([{
                        'name': 'Test Move.internal_quantity',
                        'type': 'goods',
                        'list_price': Decimal(1),
                        'cost_price': Decimal(0),
                        'category': category.id,
                        'cost_price_method': 'fixed',
                        'default_uom': kg.id,
                        }])
            product, = self.product.create([{
                        'template': template.id,
                        }])
            supplier, = self.location.search([('code', '=', 'SUP')])
            storage, = self.location.search([('code', '=', 'STO')])
            output, = self.location.search([('code', '=', 'OUT')])
            customer, = self.location.search([('code', '=', 'CUS')])
            company, = self.company.search([
                    ('rec_name', '=', 'Dunder Mifflin'),
                    ])
            currency = company.currency
            self.user.write([self.user(USER)], {
                'main_company': company.id,
                'company': company.id,
                })
            source, destination = self.move.create([{
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
            reservation, = self.reservation.create([{
                        'product': product.id,
                        'uom': kg.id,
                        'quantity': 1.0,
                        'location': storage.id,
                        'company': company.id,
                        'source': source.id,
                        'destination': destination.id,
                        }])
            for move in [source, destination]:
                self.assertRaises(UserWarning, self.move.delete, [move])

            #Check that we can write to_unit_price
            self.move.write([source, destination], {
                    'unit_price': Decimal('2.0'),
                    })
            for field, value in [
                    ('quantity', 2),
                    ('from_location', customer.id),
                    ('to_location', customer.id),
                    ]:
                for move in [source, destination]:
                    self.assertRaises(UserWarning, self.move.write, [move], {
                            field: value,
                            })


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.company.tests import test_company
    for test in test_company.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    suite.addTests(doctest.DocFileSuite('scenario_stock_reservation.rst',
            setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    suite.addTests(doctest.DocFileSuite('scenario_stock_reservation_flow.rst',
            setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite
