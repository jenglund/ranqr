import pytest
import os
import tempfile
from app import app, db

@pytest.fixture
def client():
    """Create a test client with a temporary database."""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['TESTING'] = True
    
    with app.app_context():
        db.create_all()
    
    yield app.test_client()
    
    # Cleanup
    with app.app_context():
        db.drop_all()
    os.close(db_fd)
    os.unlink(db_path)

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

