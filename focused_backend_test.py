#!/usr/bin/env python3
"""
Focused Backend Test - Testing AI endpoints specifically for reported bugs
"""
import requests
import sys
import re
import time
import json
from datetime import datetime

class FocusedAPITester:
    def __init__(self):
        self.base_url = "https://note-mutation.preview.emergentagent.com"
        self.api_url = f"{self.base_url}/api"
        self.results = []

    def test_api_health(self):
        """Quick API health check"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            if response.status_code == 200:
                print("✅ API is accessible")
                return True
            else:
                print(f"❌ API health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ API not reachable: {e}")
            return False

    def validate_latex_formatting(self, content):
        """Validate LaTeX formatting"""
        issues = []
        if '\\(' in content or '\\)' in content:
            issues.append("Found \\( \\) delimiters")
        if '\\[' in content or '\\]' in content:
            issues.append("Found \\[ \\] delimiters")
        
        # Check for raw bracket formulas
        raw_brackets = re.findall(r'^\s*\[\s*[^[\]]*\s*\]\s*$', content, re.MULTILINE)
        if raw_brackets:
            issues.append(f"Found {len(raw_brackets)} raw bracket formulas")
        return issues

    def test_fuse_beginner(self):
        """Test fuse endpoint with Beginner proficiency"""
        print("\n🔍 Testing Fusion - Beginner Level...")
        
        test_data = {
            "slide_summary": """
            Statistics Topics for Exam:
            1. Hypergeometric Distribution - sampling without replacement 
            2. Binomial Distribution - n trials with probability p
            3. Poisson Distribution - rare events with rate λ
            4. Normal Distribution - continuous bell curve  
            5. Central Limit Theorem - sample means approach normal
            """,
            "textbook_paragraph": """
            Hypergeometric distribution: P(X=k) = C(K,k) * C(N-K,n-k) / C(N,n)
            Expected value E(X) = nK/N. Used when sampling without replacement.
            """,
            "proficiency": "Beginner"
        }

        try:
            response = requests.post(
                f"{self.api_url}/fuse",
                json=test_data,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get('fused_note', '')
                
                print(f"   Response length: {len(content)} characters")
                
                # Check topic coverage
                topics = ['Hypergeometric', 'Binomial', 'Poisson', 'Normal', 'Central Limit']
                missing = [t for t in topics if t.lower() not in content.lower()]
                
                # Check LaTeX issues
                latex_issues = self.validate_latex_formatting(content)
                
                # Evaluate results
                if missing:
                    print(f"   ❌ Missing topics: {missing}")
                    self.results.append({"test": "Fusion Beginner Topics", "status": "FAIL", "details": f"Missing: {missing}"})
                else:
                    print(f"   ✅ All topics covered")
                    self.results.append({"test": "Fusion Beginner Topics", "status": "PASS"})
                
                if latex_issues:
                    print(f"   ❌ LaTeX issues: {latex_issues}")
                    self.results.append({"test": "Fusion Beginner LaTeX", "status": "FAIL", "details": latex_issues})
                else:
                    print(f"   ✅ LaTeX formatting correct")
                    self.results.append({"test": "Fusion Beginner LaTeX", "status": "PASS"})
                
                if len(content) < 800:
                    print(f"   ❌ Content too short for Beginner level")
                    self.results.append({"test": "Fusion Beginner Detail", "status": "FAIL", "details": f"Only {len(content)} chars"})
                else:
                    print(f"   ✅ Sufficient detail")
                    self.results.append({"test": "Fusion Beginner Detail", "status": "PASS"})
                    
                return True
            else:
                print(f"   ❌ API call failed: {response.status_code}")
                self.results.append({"test": "Fusion Beginner API", "status": "FAIL", "details": f"Status {response.status_code}"})
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            self.results.append({"test": "Fusion Beginner API", "status": "FAIL", "details": str(e)})
            return False

    def test_mutation_api(self):
        """Test mutation endpoint"""
        print("\n🔍 Testing Mutation API...")
        
        test_data = {
            "original_paragraph": """
            ## Hypergeometric Distribution
            
            The formula is: P(X=k) = C(K,k) * C(N-K,n-k) / C(N,n)
            Expected value: E(X) = nK/N
            """,
            "student_doubt": "Why do we use combinations in this formula?"
        }

        try:
            response = requests.post(
                f"{self.api_url}/mutate",
                json=test_data,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                mutated = data.get('mutated_paragraph', '')
                gap = data.get('concept_gap', '')
                
                print(f"   Mutated content: {len(mutated)} characters")
                print(f"   Gap diagnosis: {gap[:100]}...")
                
                # Validate mutation
                checks = []
                
                if len(mutated) > 100:
                    checks.append("Content length OK")
                    self.results.append({"test": "Mutation Content", "status": "PASS"})
                else:
                    checks.append("Content too short")
                    self.results.append({"test": "Mutation Content", "status": "FAIL"})
                
                if any(word in mutated.lower() for word in ['combination', 'choosing', 'select']):
                    checks.append("Addresses doubt")
                    self.results.append({"test": "Mutation Relevance", "status": "PASS"})
                else:
                    checks.append("Doesn't address doubt")
                    self.results.append({"test": "Mutation Relevance", "status": "FAIL"})
                
                if len(gap) > 10:
                    checks.append("Gap diagnosis present")
                    self.results.append({"test": "Mutation Gap", "status": "PASS"})
                else:
                    checks.append("No gap diagnosis")
                    self.results.append({"test": "Mutation Gap", "status": "FAIL"})
                
                latex_issues = self.validate_latex_formatting(mutated)
                if not latex_issues:
                    checks.append("LaTeX OK")
                    self.results.append({"test": "Mutation LaTeX", "status": "PASS"})
                else:
                    checks.append(f"LaTeX issues: {latex_issues}")
                    self.results.append({"test": "Mutation LaTeX", "status": "FAIL", "details": latex_issues})
                
                print(f"   Checks: {', '.join(checks)}")
                return True
                
            else:
                print(f"   ❌ API call failed: {response.status_code}")
                self.results.append({"test": "Mutation API", "status": "FAIL", "details": f"Status {response.status_code}"})
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            self.results.append({"test": "Mutation API", "status": "FAIL", "details": str(e)})
            return False

    def run_tests(self):
        """Run all focused tests"""
        print("🚀 AuraGraph AI Bug Testing")
        print(f"Testing against: {self.base_url}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.test_api_health():
            return False
            
        success_count = 0
        total_tests = 2
        
        if self.test_fuse_beginner():
            success_count += 1
            
        time.sleep(3)  # Rest between AI calls
        
        if self.test_mutation_api():
            success_count += 1
        
        # Print summary
        print(f"\n📊 Test Summary:")
        print(f"Major tests passed: {success_count}/{total_tests}")
        
        passed_results = len([r for r in self.results if r['status'] == 'PASS'])
        total_results = len(self.results)
        print(f"Detailed checks: {passed_results}/{total_results}")
        
        if passed_results < total_results:
            print("\n❌ Failed checks:")
            for result in self.results:
                if result['status'] == 'FAIL':
                    details = f" - {result.get('details', '')}" if result.get('details') else ""
                    print(f"  • {result['test']}{details}")
        
        return success_count == total_tests and passed_results >= total_results * 0.8

def main():
    tester = FocusedAPITester()
    success = tester.run_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())