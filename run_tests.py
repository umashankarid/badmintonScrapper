#!/usr/bin/env python3
"""
Pre-startup test runner
Runs all unit tests before starting the Flask app
Exits with code 1 if any tests fail, preventing deployment
"""

import sys
import unittest
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tests():
    """Run all unit tests and return True if all pass"""
    logger.info("=" * 70)
    logger.info("🧪 Running Unit Tests Before Startup")
    logger.info("=" * 70)
    
    # Discover and run all tests in test_badminton.py
    loader = unittest.TestLoader()
    suite = loader.discover('.', pattern='test_badminton.py')
    
    # Run with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    logger.info("")
    logger.info("=" * 70)
    
    if result.wasSuccessful():
        logger.info(f"✅ ALL {result.testsRun} TESTS PASSED")
        logger.info("=" * 70)
        logger.info("✅ Startup tests approved - application can start")
        logger.info("=" * 70)
        return True
    else:
        logger.error(f"❌ TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
        logger.error("=" * 70)
        
        # Print failures
        if result.failures:
            logger.error("\n❌ FAILURES:")
            for test, traceback in result.failures:
                logger.error(f"\n  {test}:")
                logger.error(f"  {traceback}")
        
        # Print errors
        if result.errors:
            logger.error("\n❌ ERRORS:")
            for test, traceback in result.errors:
                logger.error(f"\n  {test}:")
                logger.error(f"  {traceback}")
        
        logger.error("=" * 70)
        logger.error("❌ BUILD BLOCKED: Tests failed - fix issues before deployment")
        logger.error("=" * 70)
        return False

if __name__ == '__main__':
    success = run_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
