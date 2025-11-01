import pytest
import os

# CRITICAL: Set TESTING environment variable BEFORE importing app
# This ensures app.py uses test database configuration and NEVER touches production DB
# This must happen before any app imports
os.environ['TESTING'] = '1'

from app import app, db

@pytest.fixture(scope='function', autouse=True)
def test_database():
    """
    Create a temporary database for each test function.
    This ensures tests never touch the production database.
    
    NOTE: Since TESTING=1 is set before app import, app.py already uses :memory: database.
    We just need to ensure clean state for each test.
    """
    with app.app_context():
        # Drop all tables first to ensure clean state
        db.drop_all()
        # Create all tables fresh
        db.create_all()
        
        yield
        
        # Cleanup after test
        db.drop_all()
        db.session.remove()

@pytest.fixture
def client(test_database):
    """Create a test client with a temporary in-memory database."""
    return app.test_client()

@pytest.fixture
def sample_collection(client):
    """Create a sample collection with items for testing."""
    response = client.post('/api/collections', 
        json={
            'name': 'Test Collection',
            'items': 'Apple\nBanana\nCherry\nDate'
        },
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    return collection_id

