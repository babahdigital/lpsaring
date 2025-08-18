# backend/test_mikrotik_caching.py
"""
Test script untuk validasi cache performance MikroTik lookup
"""

import time
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.gateways.mikrotik_client import find_mac_by_ip_comprehensive
from app.infrastructure.gateways.mikrotik_cache import mikrotik_cache
from flask import Flask
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_app():
    """Create test Flask app with config"""
    app = Flask(__name__)
    
    # Mock config untuk testing
    app.config.update({
        'MIKROTIK_HOST': '192.168.1.1',
        'MIKROTIK_USERNAME': 'admin',
        'MIKROTIK_PASSWORD': 'password',
        'MIKROTIK_PORT': 8728,
        'MIKROTIK_API_RETRY_COUNT': 3,
        'MIKROTIK_API_RETRY_DELAY': 1,
        'MIKROTIK_PROFILE_BLOKIR': 'blokir',
        'MIKROTIK_PROFILE_HABIS': 'habis-quota',
        'MIKROTIK_FUP_ADDRESS_LIST': 'fup-users',
        'MIKROTIK_HABIS_ADDRESS_LIST': 'habis-quota',
        'MIKROTIK_BLOKIR_ADDRESS_LIST': 'blokir-users'
    })
    
    # Mock redis client for testing
    from unittest.mock import Mock
    redis_mock = Mock()
    redis_mock.ping.return_value = True
    redis_mock.get.return_value = None
    redis_mock.setex.return_value = True
    redis_mock.delete.return_value = True
    redis_mock.keys.return_value = []
    
    app.redis_client_otp = redis_mock # pyright: ignore[reportAttributeAccessIssue]
    
    return app

def test_cache_performance():
    """Test cache performance dengan multiple lookup calls"""
    app = create_test_app()
    
    with app.app_context():
        test_ip = "192.168.1.100"
        
        print(f"\n=== Testing Cache Performance for IP: {test_ip} ===")
        
        # Test 1: First call (no cache - should be slow)
        print("\n1. First call (no cache):")
        start_time = time.time()
        try:
            result1 = find_mac_by_ip_comprehensive(test_ip)
            elapsed1 = round((time.time() - start_time) * 1000, 2)
            print(f"   Result: {result1}")
            print(f"   Time: {elapsed1}ms")
        except Exception as e:
            elapsed1 = round((time.time() - start_time) * 1000, 2)
            print(f"   Error: {e}")
            print(f"   Time: {elapsed1}ms")
        
        # Test 2: Second call immediately (should use cache if available)
        print("\n2. Second call (should use cache):")
        start_time = time.time()
        try:
            result2 = find_mac_by_ip_comprehensive(test_ip)
            elapsed2 = round((time.time() - start_time) * 1000, 2)
            print(f"   Result: {result2}")
            print(f"   Time: {elapsed2}ms")
            
            if elapsed2 < elapsed1:
                improvement = round(((elapsed1 - elapsed2) / elapsed1) * 100, 1)
                print(f"   Performance improvement: {improvement}%")
            else:
                print("   No cache performance gain detected")
                
        except Exception as e:
            elapsed2 = round((time.time() - start_time) * 1000, 2)
            print(f"   Error: {e}")
            print(f"   Time: {elapsed2}ms")
        
        # Test 3: Multiple rapid calls
        print("\n3. Multiple rapid calls (testing cache consistency):")
        times = []
        for i in range(5):
            start_time = time.time()
            try:
                result = find_mac_by_ip_comprehensive(test_ip)
                elapsed = round((time.time() - start_time) * 1000, 2)
                times.append(elapsed)
                print(f"   Call {i+1}: {elapsed}ms - Success: {result[0]}")
            except Exception as e:
                elapsed = round((time.time() - start_time) * 1000, 2)
                times.append(elapsed)
                print(f"   Call {i+1}: {elapsed}ms - Error: {e}")
        
        avg_time = round(sum(times) / len(times), 2)
        print(f"   Average time: {avg_time}ms")
        
        # Test 4: Cache invalidation
        print("\n4. Cache invalidation test:")
        print("   Invalidating cache...")
        mikrotik_cache.invalidate_ip(test_ip)
        
        start_time = time.time()
        try:
            result = find_mac_by_ip_comprehensive(test_ip)
            elapsed = round((time.time() - start_time) * 1000, 2)
            print(f"   Post-invalidation call: {elapsed}ms - Success: {result[0]}")
        except Exception as e:
            elapsed = round((time.time() - start_time) * 1000, 2)
            print(f"   Post-invalidation call: {elapsed}ms - Error: {e}")

def test_cache_functionality():
    """Test basic cache functionality"""
    app = create_test_app()
    
    with app.app_context():
        print(f"\n=== Testing Cache Functionality ===")
        
        # Test direct cache operations
        test_ip = "192.168.1.101"
        test_mac = "AA:BB:CC:DD:EE:FF"
        
        # Test cache miss
        cached_result = mikrotik_cache.get_mac_by_ip(test_ip)
        print(f"1. Cache miss test: {cached_result}")
        
        # Test cache set
        mikrotik_cache.set_mac_by_ip(test_ip, True, test_mac, "Test cache entry")
        print(f"2. Cache set for IP {test_ip} with MAC {test_mac}")
        
        # Test cache hit
        cached_result = mikrotik_cache.get_mac_by_ip(test_ip)
        print(f"3. Cache hit test: {cached_result}")
        
        # Test cache invalidation
        mikrotik_cache.invalidate_ip(test_ip)
        cached_result = mikrotik_cache.get_mac_by_ip(test_ip)
        print(f"4. Post-invalidation test: {cached_result}")
        
        # Test cache clear
        mikrotik_cache.clear_all()
        print(f"5. Cache cleared")

def test_error_scenarios():
    """Test error handling scenarios"""
    app = create_test_app()
    
    with app.app_context():
        print(f"\n=== Testing Error Scenarios ===")
        
        # Test empty IP
        start_time = time.time()
        result = find_mac_by_ip_comprehensive("")
        elapsed = round((time.time() - start_time) * 1000, 2)
        print(f"1. Empty IP test: {result} ({elapsed}ms)")
        
        # Test invalid IP format
        start_time = time.time()
        result = find_mac_by_ip_comprehensive("invalid.ip.format")
        elapsed = round((time.time() - start_time) * 1000, 2)
        print(f"2. Invalid IP test: {result} ({elapsed}ms)")
        
        # Test very long IP string
        start_time = time.time()
        result = find_mac_by_ip_comprehensive("a" * 100)
        elapsed = round((time.time() - start_time) * 1000, 2)
        print(f"3. Long string test: {result} ({elapsed}ms)")

if __name__ == "__main__":
    print("Starting MikroTik Cache Performance Tests")
    print("=" * 50)
    
    try:
        test_cache_functionality()
        test_cache_performance()
        test_error_scenarios()
        
        print(f"\n=== Test Summary ===")
        print("✓ Cache functionality tests completed")
        print("✓ Performance tests completed")
        print("✓ Error scenario tests completed")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\nTests completed!")
