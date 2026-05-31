import json
from llm_service import llm_service

def test_analyze_nginx_logs():
    print("Testing with Nginx error logs...")
    nginx_logs = """
2023/10/25 12:34:56 [emerg] 12345#0: bind() to 0.0.0.0:80 failed (98: Address already in use)
2023/10/25 12:34:56 [emerg] 12345#0: bind() to 0.0.0.0:80 failed (98: Address already in use)
2023/10/25 12:34:56 [emerg] 12345#0: still could not bind()
    """
    
    result = llm_service.analyze_logs(nginx_logs)
    print("Response:")
    print(json.dumps(result, indent=2))
    
    # Assertions to verify the structure
    assert "root_cause" in result
    assert "severity" in result
    assert "recommended_fix" in result
    assert "commands" in result
    assert isinstance(result["commands"], list)
    print("Nginx Test Passed!\n")

def test_analyze_docker_logs():
    print("Testing with Docker error logs...")
    docker_logs = """
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
    """
    
    result = llm_service.analyze_logs(docker_logs)
    print("Response:")
    print(json.dumps(result, indent=2))
    
    # Assertions to verify the structure
    assert "root_cause" in result
    assert "severity" in result
    assert "recommended_fix" in result
    assert "commands" in result
    assert isinstance(result["commands"], list)
    print("Docker Test Passed!\n")

if __name__ == "__main__":
    try:
        test_analyze_nginx_logs()
        test_analyze_docker_logs()
        print("All tests completed successfully!")
    except Exception as e:
        print(f"Tests failed: {e}")
