"""
Unit tests for Database Viewer API Endpoints

Tests that verify the API endpoints can correctly read database tables
using the right endpoints with proper authentication and error handling.
"""

import unittest
from app import app


class TestDatabaseViewerEndpoints(unittest.TestCase):
    """Test database viewer API endpoints"""
    
    def setUp(self):
        """Set up Flask test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def login_as_admin(self):
        """Helper: Set admin session"""
        with self.client.session_transaction() as sess:
            sess['admin'] = True
    
    def test_get_databases_endpoint_requires_auth(self):
        """Test: GET /api/databases requires admin auth"""
        response = self.client.get('/api/databases')
        self.assertEqual(response.status_code, 401)
    
    def test_get_databases_endpoint_returns_list(self):
        """Test: GET /api/databases returns database list with admin auth"""
        self.login_as_admin()
        response = self.client.get('/api/databases')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('databases', data)
        self.assertIsInstance(data['databases'], list)
    
    def test_get_databases_endpoint_returns_statistics(self):
        """Test: GET /api/databases returns database statistics"""
        self.login_as_admin()
        response = self.client.get('/api/databases')
        data = response.get_json()
        stats = data['statistics']
        self.assertIn('total_tables', stats)
        self.assertIn('total_rows', stats)
        self.assertIn('total_size_mb', stats)
    
    def test_get_tables_endpoint_requires_auth(self):
        """Test: GET /api/database/*/tables requires admin auth"""
        response = self.client.get('/api/database/players.db/tables')
        self.assertEqual(response.status_code, 401)
    
    def test_get_tables_endpoint_returns_tables(self):
        """Test: GET /api/database/<db>/tables returns tables"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/tables')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['database'], 'players.db')
        self.assertIn('tables', data)
        self.assertIsInstance(data['tables'], list)
        self.assertGreater(len(data['tables']), 0)
    
    def test_get_tables_endpoint_returns_table_info(self):
        """Test: GET /api/database/<db>/tables returns table details"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/tables')
        data = response.get_json()
        tables = data['tables']
        
        # Verify table structure
        for table in tables:
            self.assertIn('name', table)
            self.assertIn('row_count', table)
            self.assertIn('column_count', table)
            self.assertIn('columns', table)
            # At least one table should have data
            if tables.index(table) == 0:
                self.assertGreater(table['column_count'], 0)
    
    def test_get_table_data_endpoint_requires_auth(self):
        """Test: GET /api/database/*/table/* requires admin auth"""
        response = self.client.get('/api/database/players.db/table/players')
        self.assertEqual(response.status_code, 401)
    
    def test_get_table_data_endpoint_returns_data(self):
        """Test: GET /api/database/<db>/table/<table> returns table data"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['table_name'], 'players')
        self.assertIn('columns', data)
        self.assertIn('rows', data)
        self.assertIn('pagination', data)
    
    def test_get_table_data_endpoint_returns_columns(self):
        """Test: GET /api/database/<db>/table/<table> returns columns"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players')
        data = response.get_json()
        
        # Verify columns list
        columns = data['columns']
        self.assertIsInstance(columns, list)
        self.assertGreater(len(columns), 0)
        self.assertIn('license_id', columns)
        self.assertIn('name', columns)
    
    def test_get_table_data_endpoint_returns_rows(self):
        """Test: GET /api/database/<db>/table/<table> returns data rows"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players')
        data = response.get_json()
        
        # Verify rows
        rows = data['rows']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        
        # Verify each row has expected columns
        for row in rows:
            self.assertIn('license_id', row)
            self.assertIn('name', row)
    
    def test_get_table_data_endpoint_pagination(self):
        """Test: GET /api/database/<db>/table/<table> returns pagination info"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players?page=1&page_size=10')
        data = response.get_json()
        
        # Verify pagination structure
        pagination = data['pagination']
        self.assertIn('current_page', pagination)
        self.assertIn('page_size', pagination)
        self.assertIn('total_rows', pagination)
        self.assertIn('total_pages', pagination)
        self.assertIn('has_next', pagination)
        self.assertIn('has_previous', pagination)
    
    def test_get_table_data_endpoint_search(self):
        """Test: GET /api/database/<db>/table/<table> with search parameter"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players?search=a')
        data = response.get_json()
        
        # Verify search works (should return some results with 'a')
        self.assertTrue(data['success'])
        self.assertIn('search', data)
        self.assertEqual(data['search'], 'a')
    
    def test_export_endpoint_requires_auth(self):
        """Test: Export endpoint requires admin auth"""
        response = self.client.get('/api/database/players.db/table/players/export')
        self.assertEqual(response.status_code, 401)
    
    def test_export_endpoint_json_format(self):
        """Test: Export table as JSON"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players/export?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Content-Disposition', response.headers)
        self.assertIn('players.json', response.headers['Content-Disposition'])
        # Verify it's valid JSON
        import json
        data = json.loads(response.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
    
    def test_export_endpoint_csv_format(self):
        """Test: Export table as CSV"""
        self.login_as_admin()
        response = self.client.get('/api/database/players.db/table/players/export?format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Content-Disposition', response.headers)
        self.assertIn('players.csv', response.headers['Content-Disposition'])
        content = response.data.decode('utf-8')
        self.assertIn('license_id', content)
    
    def test_manage_db_page_requires_admin(self):
        """Test: /manage-db.html requires admin login"""
        response = self.client.get('/manage-db.html', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
    
    def test_manage_db_page_accessible_to_admin(self):
        """Test: /manage-db.html is accessible to admin"""
        self.login_as_admin()
        response = self.client.get('/manage-db.html')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Database Manager', response.data)
    
    def test_read_tables_from_tournaments_db(self):
        """Test: Can read tables from tournaments.db using endpoint"""
        self.login_as_admin()
        response = self.client.get('/api/database/tournaments.db/tables')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('tables', data)
        self.assertGreater(len(data['tables']), 0)
    
    def test_read_tables_from_admin_db(self):
        """Test: Can read tables from admin.db using endpoint"""
        self.login_as_admin()
        response = self.client.get('/api/database/admin.db/tables')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('tables', data)
        self.assertGreater(len(data['tables']), 0)
    
    def test_read_complete_workflow(self):
        """
        End-to-End Test: Complete workflow of reading database tables using endpoints
        1. Get list of databases using GET /api/databases
        2. Select a database that exists
        3. List tables using GET /api/database/<db>/tables
        4. View table contents using GET /api/database/<db>/table/<table>
        5. Verify data is returned correctly with proper structure
        """
        self.login_as_admin()
        
        # Step 1: Get databases
        response = self.client.get('/api/databases')
        self.assertEqual(response.status_code, 200)
        databases = response.get_json()['databases']
        self.assertGreater(len(databases), 0)
        
        # Step 2: Find a database that exists
        existing_db = next((db for db in databases if db['exists']), None)
        self.assertIsNotNone(existing_db)
        
        # Step 3: List tables using right endpoint
        response = self.client.get(f'/api/database/{existing_db["name"]}/tables')
        self.assertEqual(response.status_code, 200)
        tables = response.get_json()['tables']
        self.assertGreater(len(tables), 0)
        
        # Step 4: View first table using right endpoint
        first_table = tables[0]
        response = self.client.get(f'/api/database/{existing_db["name"]}/table/{first_table["name"]}')
        self.assertEqual(response.status_code, 200)
        table_data = response.get_json()
        
        # Step 5: Verify data structure
        self.assertTrue(table_data['success'])
        self.assertGreater(len(table_data['columns']), 0)
        self.assertGreater(len(table_data['rows']), 0)
        self.assertIsNotNone(table_data['pagination'])


if __name__ == '__main__':
    unittest.main()
