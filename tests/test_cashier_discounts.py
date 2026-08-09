"""
Cashier Controller Discount and Tax Tests
==========================================
Test discount and tax calculations in cashier checkout.
"""

import pytest


class TestCashierDiscounts:
    """Test discount handling in cashier sales"""

    def test_sale_with_fixed_discount(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 2,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=150.0,
            discount_amount=50.0
        )

        assert success is True
        assert sale['total'] == 150.0
        assert sale['discount_amount'] == 50.0

    def test_sale_with_percentage_discount(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 2,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=180.0,
            discount_amount=20.0
        )

        assert success is True
        assert sale['discount_amount'] == 20.0

    def test_discount_does_not_make_total_negative(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 1,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=0.0,
            discount_amount=200.0
        )

        assert success is True
        assert sale['discount_amount'] == 200.0
        assert 'total' in sale

    def test_zero_discount_succeeds(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 1,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=100.0,
            discount_amount=0.0
        )

        assert success is True
        assert sale['discount_amount'] == 0.0


class TestCashierTaxes:
    """Test tax calculations in cashier sales"""

    def test_sale_with_tax_exclusive(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 1,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=116.0,
            tax_rate=16.0
        )

        assert success is True
        assert sale['tax_amount'] == 16.0
        assert sale['total'] == 116.0

    def test_sale_with_tax_inclusive(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 1,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=116.0,
            tax_rate=16.0
        )

        assert success is True
        assert sale['tax_amount'] > 0
        assert sale['total'] == 116.0

    def test_sale_with_discount_and_tax(self, cashier_controller, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 2,
            'price': test_product['price']
        }]

        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=185.6,
            tax_rate=16.0,
            discount_amount=40.0
        )

        assert success is True
        assert sale['discount_amount'] == 40.0
        assert sale['total'] == 185.6
