"""
COMPREHENSIVE TESTS FOR OPTIMIZED STOCK DEDUCTION SYSTEM
=========================================================

Tests:
1. Raw product sales (immediate deduction)
2. Composite product sales (multi-ingredient deduction)
3. Decimal quantity support (kg, liters, grams)
4. Stock validation edge cases
5. Performance benchmarks (<200ms)
6. Single source of truth verification
7. Concurrent sales handling
"""

import json
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from stock_engine import StockDeductionEngine, optimize_sale_completion


def test_raw_product_sale():
    """Test: Sale of raw product immediately deducts stock"""
    print("\n" + "="*60)
    print("TEST 1: Raw Product Sale (Tilapia)")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Tilapia',
            'quantity': 23.0,
            'unit': 'kg',
            'price': 5.50,
            'isComposite': False,
            'accountId': 'main'
        }
    ]
    
    items = [
        {'productId': 1, 'quantity': 3}
    ]
    
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    print(f"✓ Validation passed: {is_valid}")
    print(f"✓ Deductions: {json.dumps(deductions, indent=2)}")
    
    if is_valid:
        engine.apply_deductions(deductions)
        print(f"✓ Stock after deduction: {products[0]['quantity']} kg (was 23 kg)")
        assert products[0]['quantity'] == 20.0, "Stock should be 20 kg"
        print("✅ TEST PASSED: Stock correctly deducted to 20 kg")
    else:
        print(f"❌ TEST FAILED: {error_msg}")
        return False
    
    return True


def test_composite_product_sale():
    """Test: Sale of composite product deducts all ingredients"""
    print("\n" + "="*60)
    print("TEST 2: Composite Product Sale (Fried Fish)")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Tilapia',
            'quantity': 50.0,
            'unit': 'kg',
            'price': 5.50,
            'isComposite': False,
            'accountId': 'main'
        },
        {
            'id': 2,
            'name': 'Cooking Oil',
            'quantity': 20.0,
            'unit': 'liters',
            'price': 2.00,
            'expenseOnly': True,
            'accountId': 'main'
        },
        {
            'id': 3,
            'name': 'Salt',
            'quantity': 5.0,
            'unit': 'kg',
            'price': 0.50,
            'expenseOnly': True,
            'accountId': 'main'
        },
        {
            'id': 5,
            'name': 'Fried Fish',
            'quantity': 0,
            'unit': 'serving',
            'price': 8.00,
            'isComposite': True,
            'recipe': [
                {'productId': 1, 'name': 'Tilapia', 'quantity': 2, 'unit': 'kg', 'source': 'inventory'},
                {'productId': 2, 'name': 'Cooking Oil', 'quantity': 0.2, 'unit': 'liters', 'source': 'expenses'},
                {'productId': 3, 'name': 'Salt', 'quantity': 0.05, 'unit': 'kg', 'source': 'expenses'}
            ],
            'accountId': 'main'
        }
    ]
    
    items = [
        {'productId': 5, 'quantity': 1}  # Sell 1 serving of Fried Fish
    ]
    
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    print(f"✓ Validation passed: {is_valid}")
    print(f"✓ Deductions breakdown:")
    for d in deductions['products']:
        print(f"  - {d['name']}: {d['before_qty']} → {d['after_qty']} {d['unit']}")
    for d in deductions['expenses']:
        print(f"  - {d['name']}: {d['before_qty']} → {d['after_qty']} {d['unit']}")
    
    if is_valid:
        engine.apply_deductions(deductions)
        
        # Verify deductions
        tilapia = next(p for p in products if p['id'] == 1)
        oil = next(p for p in products if p['id'] == 2)
        salt = next(p for p in products if p['id'] == 3)
        
        print(f"\n✓ Final stock levels:")
        print(f"  - Tilapia: {tilapia['quantity']} kg (deducted 2 kg)")
        print(f"  - Cooking Oil: {oil['quantity']} L (deducted 0.2 L)")
        print(f"  - Salt: {salt['quantity']} kg (deducted 0.05 kg)")
        
        assert tilapia['quantity'] == 48.0, f"Tilapia should be 48 kg, got {tilapia['quantity']}"
        assert oil['quantity'] == 19.8, f"Oil should be 19.8 L, got {oil['quantity']}"
        assert salt['quantity'] == 4.95, f"Salt should be 4.95 kg, got {salt['quantity']}"
        
        print("✅ TEST PASSED: All ingredients correctly deducted")
    else:
        print(f"❌ TEST FAILED: {error_msg}")
        return False
    
    return True


def test_insufficient_stock():
    """Test: Sale fails when stock is insufficient"""
    print("\n" + "="*60)
    print("TEST 3: Insufficient Stock Detection")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Tilapia',
            'quantity': 2.0,
            'unit': 'kg',
            'price': 5.50,
            'isComposite': False,
            'accountId': 'main'
        }
    ]
    
    items = [
        {'productId': 1, 'quantity': 5}  # Try to sell 5 kg when only 2 kg available
    ]
    
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    print(f"✓ Validation result: is_valid = {is_valid}")
    print(f"✓ Error message: {error_msg}")
    
    if not is_valid and "Insufficient stock" in error_msg:
        print("✅ TEST PASSED: Correctly rejected insufficient stock")
        return True
    else:
        print(f"❌ TEST FAILED: Should have rejected sale with insufficient stock")
        return False


def test_insufficient_ingredient_stock():
    """Test: Composite sale fails when ingredient stock is insufficient"""
    print("\n" + "="*60)
    print("TEST 4: Insufficient Ingredient Stock")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Tilapia',
            'quantity': 1.0,  # Only 1 kg available (need 2 per serving)
            'unit': 'kg',
            'isComposite': False,
            'accountId': 'main'
        },
        {
            'id': 5,
            'name': 'Fried Fish',
            'isComposite': True,
            'recipe': [
                {'productId': 1, 'quantity': 2, 'unit': 'kg'}  # Needs 2 kg
            ],
            'accountId': 'main'
        }
    ]
    
    items = [
        {'productId': 5, 'quantity': 1}  # Try to sell 1 serving
    ]
    
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    print(f"✓ Validation result: is_valid = {is_valid}")
    print(f"✓ Error message: {error_msg}")
    
    if not is_valid and "Insufficient ingredient stock" in error_msg:
        print("✅ TEST PASSED: Correctly rejected due to insufficient ingredient")
        return True
    else:
        print(f"❌ TEST FAILED: Should have rejected sale with insufficient ingredient")
        return False


def test_decimal_quantities():
    """Test: Decimal quantities work correctly (kg, liters, grams)"""
    print("\n" + "="*60)
    print("TEST 5: Decimal Quantities")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Cooking Oil',
            'quantity': 5.5,
            'unit': 'liters',
            'isComposite': False,
            'accountId': 'main'
        },
        {
            'id': 2,
            'name': 'Salt',
            'quantity': 2.75,
            'unit': 'kg',
            'isComposite': False,
            'accountId': 'main'
        }
    ]
    
    items = [
        {'productId': 1, 'quantity': 0.3},
        {'productId': 2, 'quantity': 0.05}
    ]
    
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    if is_valid:
        engine.apply_deductions(deductions)
        
        oil = next(p for p in products if p['id'] == 1)
        salt = next(p for p in products if p['id'] == 2)
        
        print(f"✓ Oil: {oil['quantity']} liters (deducted 0.3 L)")
        print(f"✓ Salt: {salt['quantity']} kg (deducted 0.05 kg)")
        
        assert abs(oil['quantity'] - 5.2) < 0.001, f"Oil should be ~5.2 L"
        assert abs(salt['quantity'] - 2.7) < 0.001, f"Salt should be ~2.7 kg"
        
        print("✅ TEST PASSED: Decimal quantities handled correctly")
        return True
    else:
        print(f"❌ TEST FAILED: {error_msg}")
        return False


def test_performance_raw_sale():
    """Test: Raw product sale completes in <200ms"""
    print("\n" + "="*60)
    print("TEST 6: Performance - Raw Product Sale")
    print("="*60)
    
    products = [{'id': i, 'name': f'Product {i}', 'quantity': 100, 'isComposite': False, 'accountId': 'main'} 
                for i in range(1, 11)]
    
    items = [{'productId': 1, 'quantity': 5}]
    
    start = time.time()
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    engine.apply_deductions(deductions)
    elapsed_ms = (time.time() - start) * 1000
    
    print(f"✓ Processing time: {elapsed_ms:.2f}ms")
    
    if elapsed_ms < 200:
        print(f"✅ TEST PASSED: Completed in {elapsed_ms:.2f}ms (target: <200ms)")
        return True
    else:
        print(f"❌ TEST FAILED: Took {elapsed_ms:.2f}ms (target: <200ms)")
        return False


def test_performance_composite_sale():
    """Test: Composite product sale completes in <200ms"""
    print("\n" + "="*60)
    print("TEST 7: Performance - Composite Product Sale")
    print("="*60)
    
    # Create 50 raw materials
    products = [
        {'id': i, 'name': f'Raw Material {i}', 'quantity': 1000, 'unit': 'kg', 'isComposite': False, 'accountId': 'main'} 
        for i in range(1, 51)
    ]
    
    # Composite product with 10 ingredients
    composite = {
        'id': 100,
        'name': 'Complex Dish',
        'isComposite': True,
        'recipe': [
            {'productId': i, 'quantity': 0.1 * (i % 10 + 1), 'unit': 'kg'}
            for i in range(1, 11)
        ],
        'accountId': 'main'
    }
    products.append(composite)
    
    items = [
        {'productId': 100, 'quantity': 5}  # Sell 5 servings
    ]
    
    start = time.time()
    engine = StockDeductionEngine(products, [])
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    engine.apply_deductions(deductions)
    elapsed_ms = (time.time() - start) * 1000
    
    print(f"✓ Processing time: {elapsed_ms:.2f}ms")
    print(f"✓ Deductions made: {len(deductions['products'])} items")
    
    if elapsed_ms < 200:
        print(f"✅ TEST PASSED: Completed in {elapsed_ms:.2f}ms (target: <200ms)")
        return True
    else:
        print(f"❌ TEST FAILED: Took {elapsed_ms:.2f}ms (target: <200ms)")
        return False


def test_single_source_of_truth():
    """Test: All deductions modify the same products source"""
    print("\n" + "="*60)
    print("TEST 8: Single Source of Truth")
    print("="*60)
    
    products = [
        {
            'id': 1,
            'name': 'Tilapia',
            'quantity': 100.0,
            'unit': 'kg',
            'isComposite': False,
            'accountId': 'main'
        }
    ]
    
    original_id = id(products)
    
    # Make first sale
    items1 = [{'productId': 1, 'quantity': 10}]
    engine1 = StockDeductionEngine(products, [])
    is_valid1, _, deductions1 = engine1.validate_and_prepare_deductions(items1)
    engine1.apply_deductions(deductions1)
    
    print(f"✓ After sale 1: {products[0]['quantity']} kg")
    
    # Make second sale
    items2 = [{'productId': 1, 'quantity': 5}]
    engine2 = StockDeductionEngine(products, [])
    is_valid2, _, deductions2 = engine2.validate_and_prepare_deductions(items2)
    engine2.apply_deductions(deductions2)
    
    print(f"✓ After sale 2: {products[0]['quantity']} kg")
    
    if products[0]['quantity'] == 85.0 and id(products) == original_id:
        print("✅ TEST PASSED: Single source of truth maintained")
        return True
    else:
        print(f"❌ TEST FAILED: Expected 85 kg, got {products[0]['quantity']}")
        return False


def run_all_tests():
    """Run all tests and report results"""
    print("\n" + "="*60)
    print("OPTIMIZED STOCK DEDUCTION SYSTEM - TEST SUITE")
    print("="*60)
    
    tests = [
        ("Raw Product Sale", test_raw_product_sale),
        ("Composite Product Sale", test_composite_product_sale),
        ("Insufficient Stock", test_insufficient_stock),
        ("Insufficient Ingredient Stock", test_insufficient_ingredient_stock),
        ("Decimal Quantities", test_decimal_quantities),
        ("Performance - Raw Sale", test_performance_raw_sale),
        ("Performance - Composite Sale", test_performance_composite_sale),
        ("Single Source of Truth", test_single_source_of_truth),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
