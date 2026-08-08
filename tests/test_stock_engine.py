"""
Stock Engine Tests
==================
Test stock calculations, batch tracking, and inventory logic.
"""

import pytest
from datetime import datetime, timedelta


class TestStockEngineCalculations:
    """Test stock engine calculations"""

    def test_get_low_stock_products(self, stock_engine, test_account):
        products = stock_engine.get_low_stock_products(test_account['account_id'])
        assert isinstance(products, list)

    def test_get_out_of_stock_products(self, stock_engine, test_account):
        products = stock_engine.get_out_of_stock_products(test_account['account_id'])
        assert isinstance(products, list)

    def test_adjust_stock(self, stock_engine, test_account, test_product):
        success = stock_engine.adjust_stock(
            product_id=test_product['id'],
            quantity=10.0,
            account_id=test_account['account_id'],
            movement_type='adjustment',
            notes='test adjustment'
        )
        assert isinstance(success, bool)

    def test_get_stock_deduction_log(self, stock_engine, test_account):
        logs = stock_engine.get_stock_deduction_log(test_account['account_id'])
        assert isinstance(logs, list)


class TestStockEngineSales:
    """Test stock engine sale preparation and execution"""

    def test_validate_and_prepare_sale(self, stock_engine, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 2,
            'price': test_product['price']
        }]
        result = stock_engine.validate_and_prepare_sale(
            account_id=test_account['account_id'],
            items=items
        )
        assert isinstance(result, (dict, tuple))

    def test_execute_sale(self, stock_engine, test_account, test_product):
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 1,
            'price': test_product['price']
        }]
        result = stock_engine.execute_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=100.0
        )
        assert isinstance(result, (dict, tuple))
