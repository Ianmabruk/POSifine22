"""
Product Management Tests
========================
Test product CRUD operations, stock management, and composite products.
"""

import pytest


class TestProductCreation:
    """Test product creation"""
    
    def test_create_simple_product(self, admin_controller, test_account):
        """Test creating a simple product"""
        success, error, product = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Simple Product',
            price=50.0,
            cost=25.0,
            quantity=100.0,
            category='electronics'
        )
        
        assert success is True
        assert error is None
        assert product is not None
        assert product['name'] == 'Simple Product'
        assert product['price'] == 50.0
        assert product['quantity'] == 100.0
    
    def test_create_composite_product(self, admin_controller, test_account):
        """Test creating a composite product with recipe"""
        # First create ingredient products
        _, _, flour = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Flour',
            price=10.0,
            cost=5.0,
            quantity=1000.0,
            unit='kg'
        )
        
        _, _, sugar = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Sugar',
            price=8.0,
            cost=4.0,
            quantity=500.0,
            unit='kg'
        )
        
        # Create composite product (cake)
        recipe = [
            {'product_id': flour['id'], 'quantity': 0.5},  # 500g flour
            {'product_id': sugar['id'], 'quantity': 0.2}   # 200g sugar
        ]
        
        success, error, cake = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Cake',
            price=100.0,
            quantity=0.0,  # Composite products track components
            is_composite=True,
            recipe=recipe
        )
        
        assert success is True
        assert cake['is_composite'] is True
        assert len(cake['recipe']) == 2


class TestProductRetrieval:
    """Test product retrieval operations"""
    
    def test_get_all_products(self, admin_controller, test_account, test_product):
        """Test getting all products for an account"""
        products = admin_controller.get_products(test_account['account_id'])
        
        assert isinstance(products, list)
        assert len(products) > 0
        assert any(p['id'] == test_product['id'] for p in products)
    
    def test_get_product_by_id(self, datastore, test_account, test_product):
        """Test getting a specific product by ID"""
        product = datastore.get_by_id('products', test_product['id'], test_account['account_id'])
        
        assert product is not None
        assert product['id'] == test_product['id']
        assert product['name'] == test_product['name']


class TestProductUpdate:
    """Test product update operations"""
    
    def test_update_product_price(self, admin_controller, datastore, test_account, test_product):
        """Test updating product price"""
        new_price = 150.0
        success, error, updated = admin_controller.update_product(
            product_id=test_product['id'],
            account_id=test_account['account_id'],
            price=new_price
        )
        
        assert success is True
        assert updated['price'] == new_price
    
    def test_update_product_stock(self, admin_controller, datastore, test_account, test_product):
        """Test updating product stock quantity"""
        new_quantity = 200.0
        success, error = admin_controller.update_stock(
            product_id=test_product['id'],
            account_id=test_account['account_id'],
            quantity=new_quantity
        )
        
        assert success is True
        
        # Verify stock updated
        product = datastore.get_by_id('products', test_product['id'], test_account['account_id'])
        assert product['quantity'] == new_quantity


class TestProductDeletion:
    """Test product deletion"""
    
    def test_delete_product(self, admin_controller, datastore, test_account):
        """Test deleting a product"""
        # Create product to delete
        _, _, product = admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Product To Delete',
            price=10.0,
            quantity=50.0
        )
        
        # Delete it
        success, error = admin_controller.delete_product(
            product_id=product['id'],
            account_id=test_account['account_id']
        )
        
        assert success is True
        
        # Verify it's deleted
        deleted_product = datastore.get_by_id('products', product['id'], test_account['account_id'])
        assert deleted_product is None


class TestLowStockAlerts:
    """Test low stock alert functionality"""
    
    def test_low_stock_detection(self, admin_controller, test_account):
        """Test that low stock products are detected"""
        # Create product with low stock
        admin_controller.create_product(
            account_id=test_account['account_id'],
            created_by=test_account['user_id'],
            name='Low Stock Item',
            price=20.0,
            quantity=5.0,
            reorder_level=10.0  # Stock below reorder level
        )
        
        warnings = admin_controller.check_low_stock(test_account['account_id'])
        
        assert isinstance(warnings, list)
        assert len(warnings) > 0
        assert any('Low Stock Item' in w['name'] for w in warnings)
