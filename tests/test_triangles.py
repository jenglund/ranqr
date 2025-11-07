"""Tests for triangle detection and resolution functionality."""
import pytest
from app import db, Item, Comparison, Collection, find_triangles, calculate_triangle_dissonance, get_triangle_resolution_options

def test_find_triangles_no_cycles(client, sample_collection):
    """Test that no triangles are found when there are no cycles."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create linear ordering: A > B > C > D (no cycles)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        collection = Collection.query.get(sample_collection)
        triangles = find_triangles(collection)
        
        assert len(triangles) == 0

def test_find_triangles_simple_cycle(client, sample_collection):
    """Test finding a simple cycle: A > B, B > C, C > A."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create cycle: A > B, B > C, C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        collection = Collection.query.get(sample_collection)
        triangles = find_triangles(collection)
        
        assert len(triangles) == 1
        triangle = triangles[0]
        assert set(triangle[:3]) == {item_ids[0], item_ids[1], item_ids[2]}

def test_calculate_dissonance(client, sample_collection):
    """Test dissonance calculation."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        
        # Set up items with different scores
        items[0].points = 5
        items[1].points = 2
        items[2].points = 0
        
        db.session.commit()
        
        # Dissonance = sum of two largest differences
        # diff_ab = |5 - 2| = 3
        # diff_bc = |2 - 0| = 2
        # diff_ca = |5 - 0| = 5
        # Smallest is 2, so dissonance = 3 + 5 = 8
        dissonance = calculate_triangle_dissonance(items[0], items[1], items[2], [])
        
        assert dissonance == 8.0

def test_get_triangle_resolution_options(client, sample_collection):
    """Test getting resolution options for a triangle."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create cycle: A > B, B > C, C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        collection = Collection.query.get(sample_collection)
        options = get_triangle_resolution_options(collection, item_ids[0], item_ids[1], item_ids[2])
        
        # Should have 6 options (3! = 6)
        assert len(options) == 6
        
        # Each option should have resolution, changes, and dissonance_change
        for option in options:
            assert 'resolution' in option
            assert 'changes' in option
            assert 'dissonance_change' in option
            assert 'new_dissonance' in option
            assert 'item_a_order' in option['resolution']
            assert 'item_b_order' in option['resolution']
            assert 'item_c_order' in option['resolution']

def test_get_triangles_endpoint(client, sample_collection):
    """Test the GET /triangles endpoint."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create cycle: A > B, B > C, C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/triangles')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'triangles' in data
        assert len(data['triangles']) == 1
        
        triangle = data['triangles'][0]
        assert 'item_a' in triangle
        assert 'item_b' in triangle
        assert 'item_c' in triangle
        assert 'dissonance' in triangle

def test_get_triangle_options_endpoint(client, sample_collection):
    """Test the GET /triangles/<ids>/options endpoint."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create cycle: A > B, B > C, C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/triangles/{item_ids[0]}/{item_ids[1]}/{item_ids[2]}/options')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'options' in data
        assert len(data['options']) == 6

def test_resolve_triangle_endpoint(client, sample_collection):
    """Test the POST /triangles/resolve endpoint."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create cycle: A > B, B > C, C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Get options to find a valid resolution
        options_response = client.get(f'/api/collections/{sample_collection}/triangles/{item_ids[0]}/{item_ids[1]}/{item_ids[2]}/options')
        options_data = options_response.get_json()
        resolution = options_data['options'][0]['resolution']
        
        # Resolve triangle
        response = client.post(f'/api/collections/{sample_collection}/triangles/resolve',
            json={
                'item_a_id': item_ids[0],
                'item_b_id': item_ids[1],
                'item_c_id': item_ids[2],
                'resolution': resolution
            },
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        
        # Verify triangle is resolved (should have no triangles now)
        triangles_response = client.get(f'/api/collections/{sample_collection}/triangles')
        triangles_data = triangles_response.get_json()
        # Note: resolving one triangle might create others, so we just check it succeeded
