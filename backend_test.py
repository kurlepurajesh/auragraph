import requests
import json
import sys
from datetime import datetime
import time

class AuraGraphAPITester:
    def __init__(self, base_url="https://note-mutation.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                if files:
                    # Remove Content-Type for file uploads
                    if 'Content-Type' in test_headers:
                        del test_headers['Content-Type']
                    response = requests.post(url, files=files, data=data, headers=test_headers)
                else:
                    response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=test_headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json() if response.content else {}
                except:
                    return True, {}
            else:
                self.failed_tests.append({
                    'test': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:200] if response.text else 'No response'
                })
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            self.failed_tests.append({
                'test': name,
                'expected': expected_status,
                'actual': 'Exception',
                'response': str(e)
            })
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test health check endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "health",
            200
        )
        return success and response.get('status') == 'ok'

    def test_register_user(self, email, password):
        """Test user registration"""
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['id']
            return True
        return False

    def test_login_user(self, email, password):
        """Test user login"""
        success, response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['id']
            return True
        return False

    def test_create_notebook(self, name, course):
        """Test notebook creation"""
        success, response = self.run_test(
            "Create Notebook",
            "POST",
            "notebooks",
            200,
            data={"name": name, "course": course}
        )
        return response.get('id') if success else None

    def test_list_notebooks(self):
        """Test listing notebooks"""
        success, response = self.run_test(
            "List Notebooks",
            "GET",
            "notebooks",
            200
        )
        return response if success else []

    def test_fetch_notebook(self, notebook_id):
        """Test fetching specific notebook"""
        success, response = self.run_test(
            "Fetch Notebook",
            "GET",
            f"notebooks/{notebook_id}",
            200
        )
        return success

    def test_save_notebook_note(self, notebook_id, note, proficiency="Intermediate"):
        """Test saving notebook note"""
        success, response = self.run_test(
            "Save Notebook Note",
            "PATCH",
            f"notebooks/{notebook_id}/note",
            200,
            data={"note": note, "proficiency": proficiency}
        )
        return success

    def test_delete_notebook(self, notebook_id):
        """Test deleting notebook"""
        success, response = self.run_test(
            "Delete Notebook",
            "DELETE",
            f"notebooks/{notebook_id}",
            200
        )
        return success

    def test_knowledge_fusion(self):
        """Test knowledge fusion endpoint"""
        test_data = {
            "slide_summary": "Introduction to Digital Signal Processing: Signals are mathematical functions that represent physical quantities. Key concepts include continuous-time and discrete-time signals.",
            "textbook_paragraph": "Digital Signal Processing involves the manipulation of signals using computational algorithms. The field encompasses signal acquisition, transformation, filtering, and reconstruction.",
            "proficiency": "Intermediate"
        }
        
        success, response = self.run_test(
            "Knowledge Fusion",
            "POST",
            "fuse",
            200,
            data=test_data
        )
        return success and 'fused_note' in response

    def test_note_mutation(self):
        """Test note mutation endpoint"""
        test_data = {
            "original_paragraph": "The Fourier Transform decomposes a signal into its frequency components.",
            "student_doubt": "I don't understand why we need frequency components. What's the practical use?"
        }
        
        success, response = self.run_test(
            "Note Mutation",
            "POST",
            "mutate",
            200,
            data=test_data
        )
        return success and 'mutated_paragraph' in response

    def test_concept_examiner(self):
        """Test examiner endpoint"""
        test_data = {
            "concept_name": "Fourier Transform"
        }
        
        success, response = self.run_test(
            "Concept Examiner",
            "POST",
            "examine",
            200,
            data=test_data
        )
        return success and 'practice_questions' in response

    def test_concept_extraction(self):
        """Test concept extraction endpoint"""
        test_data = {
            "note": "# Digital Signal Processing\n\n## Fourier Transform\nThe Fourier Transform is fundamental to signal analysis.\n\n## Convolution\nConvolution is used for filtering operations."
        }
        
        success, response = self.run_test(
            "Concept Extraction",
            "POST",
            "extract-concepts",
            200,
            data=test_data
        )
        return success and 'nodes' in response

    def test_notebook_graph_operations(self, notebook_id):
        """Test notebook graph operations"""
        # Get graph
        success1, _ = self.run_test(
            "Get Notebook Graph",
            "GET",
            f"notebooks/{notebook_id}/graph",
            200
        )
        
        # Update graph node
        success2, _ = self.run_test(
            "Update Graph Node",
            "POST",
            f"notebooks/{notebook_id}/graph/update",
            200,
            data={"concept_name": "Test Concept", "status": "mastered"}
        )
        
        return success1

def main():
    print("🚀 Starting AuraGraph API Testing...")
    print(f"🕒 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize tester
    tester = AuraGraphAPITester()
    
    # Test credentials
    test_email = "test@iitr.ac.in"
    test_password = "test123"
    
    # Test sequence
    print("\n" + "="*60)
    print("PHASE 1: BASIC CONNECTIVITY & AUTH")
    print("="*60)
    
    # 1. Health check
    if not tester.test_health_check():
        print("❌ Backend health check failed - stopping tests")
        return 1
    
    # 2. Test login with existing user
    if not tester.test_login_user(test_email, test_password):
        print("❌ Login with test user failed - stopping tests")
        return 1
    
    print("\n" + "="*60)
    print("PHASE 2: NOTEBOOK OPERATIONS")
    print("="*60)
    
    # 3. Create notebook
    notebook_id = tester.test_create_notebook("Test Notebook", "CS101")
    if not notebook_id:
        print("❌ Notebook creation failed")
        return 1
    
    # 4. List notebooks
    if not tester.test_list_notebooks():
        print("❌ Listing notebooks failed")
    
    # 5. Fetch specific notebook
    if not tester.test_fetch_notebook(notebook_id):
        print("❌ Fetching notebook failed")
    
    # 6. Save notebook note
    test_note = "# Digital Signal Processing\n\nThis is a test note for DSP concepts."
    if not tester.test_save_notebook_note(notebook_id, test_note):
        print("❌ Saving notebook note failed")
    
    print("\n" + "="*60)
    print("PHASE 3: AI AGENT ENDPOINTS")
    print("="*60)
    
    # 7. Test AI endpoints
    if not tester.test_knowledge_fusion():
        print("⚠️ Knowledge fusion failed (may be expected if LLM key is invalid)")
    
    if not tester.test_note_mutation():
        print("⚠️ Note mutation failed (may be expected if LLM key is invalid)")
    
    if not tester.test_concept_examiner():
        print("⚠️ Concept examiner failed (may be expected if LLM key is invalid)")
    
    if not tester.test_concept_extraction():
        print("❌ Concept extraction failed")
    
    print("\n" + "="*60)
    print("PHASE 4: GRAPH OPERATIONS")
    print("="*60)
    
    # 8. Test graph operations
    if not tester.test_notebook_graph_operations(notebook_id):
        print("❌ Graph operations failed")
    
    print("\n" + "="*60)
    print("PHASE 5: CLEANUP")
    print("="*60)
    
    # 9. Delete test notebook
    if not tester.test_delete_notebook(notebook_id):
        print("❌ Deleting notebook failed")
    
    # Print final results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"📊 Tests passed: {tester.tests_passed}/{tester.tests_run} ({success_rate:.1f}%)")
    
    if tester.failed_tests:
        print(f"\n❌ Failed tests ({len(tester.failed_tests)}):")
        for failure in tester.failed_tests:
            print(f"  • {failure['test']}: Expected {failure['expected']}, got {failure['actual']}")
            if len(failure['response']) > 0:
                print(f"    Response: {failure['response'][:100]}...")
    
    print(f"\n🕒 Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Return appropriate exit code
    return 0 if success_rate >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())