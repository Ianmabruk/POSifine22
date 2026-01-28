"""
Sales Transaction Tests
=======================
Test complete sale operations, stock deduction, and sales analytics.
"""

import pytest


class TestCompleteSale:
    """Test complete sale operation"""
    
    def test_simple_sale(self, cashier_controller, test_account, test_product):
        """Test completing a simple sale"""
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 5,
            'price': test_product['price']
        }]
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=500.0
        )
        
        assert success is True
        assert error is None
        assert sale is not None
        assert sale['total'] == 500.0  # 5 items × 100.0
        assert len(sale['items']) == 1
    
    def test_sale_with_multiple_items(self, cashier_controller, admin_controller, test_account, test_product):
        """Test sale with multiple different products"""
        # Create second product
        _, _, product2 = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Product 2',
            price=75.0,
            cost=35.0,
            quantity=50.0
        )
        
        items = [
            {
                'product_id': test_product['id'],
                'name': test_product['name'],
                'quantity': 2,
                'price': test_product['price']
            },
            {
                'product_id': product2['id'],
                'name': product2['name'],
                'quantity': 3,
                'price': product2['price']
            }
        ]
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='mpesa',
            amount_paid=425.0
        )
        
        assert success is True
        assert sale['total'] == 425.0  # (2 × 100) + (3 × 75)
        assert len(sale['items']) == 2
    
    def test_sale_with_insufficient_stock(self, cashier_controller, admin_controller, test_account):
        """Test that sale fails when stock is insufficient"""
        # Create product with limited stock
        _, _, limited_product = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Limited Stock',
            price=50.0,
            cost=25.0,
            quantity=3.0  # Only 3 in stock
        )
        
        items = [{
            'product_id': limited_product['id'],
            'name': limited_product['name'],
            'quantity': 10,  # Trying to sell 10
            'price': limited_product['price']
        }]
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=500.0
        )
        
        assert success is False
        assert error is not None
        assert 'insufficient' in error.lower() or 'stock' in error.lower()


class TestStockDeduction:
    """Test stock deduction during sales"""
    
    def test_stock_deducted_after_sale(self, cashier_controller, datastore, test_account, test_product):
        """Test that stock is properly deducted after sale"""
        initial_quantity = test_product['quantity']
        sold_quantity = 10
        
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': sold_quantity,
            'price': test_product['price']
        }]
        
        cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=1000.0
        )
        
        # Check stock after sale
        updated_product = datastore.get_by_id('products', test_product['id'], test_account['account_id'])
        expected_quantity = initial_quantity - sold_quantity
        
        assert updated_product['quantity'] == expected_quantity


class TestSalesAnalytics:
    """Test sales analytics and reporting"""
    
    def test_get_sales_list(self, cashier_controller, admin_controller, test_account, test_product):
        """Test retrieving list of sales"""
        # Make a sale
        items = [{'product_id': test_product['id'], 'name': test_product['name'], 'quantity': 2, 'price': test_product['price']}]
        cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=200.0
        )
        
        # Get sales
        sales = admin_controller.get_sales(test_account['account_id'])
        
        assert isinstance(sales, list)
        assert len(sales) > 0
    
    def test_sales_profit_calculation(self, cashier_controller, test_account, test_product):
        """Test that profit is calculated correctly"""
        items = [{
            'product_id': test_product['id'],
            'name': test_product['name'],
            'quantity': 10,
            'price': test_product['price'],
            'cost': test_product['cost']
        }]
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=1000.0
        )
        
        expected_revenue = 10 * test_product['price']  # 10 × 100 = 1000
        expected_cost = 10 * test_product['cost']      # 10 × 50 = 500
        expected_profit = expected_revenue - expected_cost  # 500
        
        assert sale['total'] == expected_revenue
        assert sale['total_cost'] == expected_cost
        assert sale['gross_profit'] == expected_profit


class TestPaymentMethods:
    """Test different payment methods"""
    
    def test_cash_payment(self, cashier_controller, test_account, test_product):
        """Test cash payment with change calculation"""
        items = [{'product_id': test_product['id'], 'name': test_product['name'], 'quantity': 3, 'price': test_product['price']}]
        amount_paid = 400.0
        expected_total = 300.0
        expected_change = 100.0
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='cash',
            amount_paid=amount_paid
        )
        
        assert success is True
        assert sale['payment_method'] == 'cash'
        assert sale['amount_paid'] == amount_paid
        assert sale['change'] == expected_change
    
    def test_mpesa_payment(self, cashier_controller, test_account, test_product):
        """Test M-Pesa mobile payment"""
        items = [{'product_id': test_product['id'], 'name': test_product['name'], 'quantity': 1, 'price': test_product['price']}]
        
        success, error, sale = cashier_controller.complete_sale(
            account_id=test_account['account_id'],
            cashier_id=test_account['user_id'],
            cashier_name='Test Cashier',
            items=items,
            payment_method='mpesa',
            amount_paid=100.0
        )
        
        assert success is True
        assert sale['payment_method'] == 'mpesa'
