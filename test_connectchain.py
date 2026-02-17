"""Test script to validate ConnectChain configuration.

This script verifies that ConnectChain is properly configured and can
make successful API calls.

Usage:
    python test_connectchain.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import settings
from src.llm import get_llm_client, connectchain_client


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_configuration():
    """Check that required configuration is present."""
    print_section("Configuration Check")

    required_settings = [
        ("llm.use_connectchain", "ConnectChain enabled"),
        ("connectchain.config_path", "ConnectChain config path"),
        ("schema.schema_directory", "Schema directory"),
    ]

    all_ok = True

    for setting_key, description in required_settings:
        try:
            value = settings.get(setting_key)
            print(f"✅ {description}: {value}")
        except ValueError as e:
            print(f"❌ {description}: NOT SET")
            all_ok = False

    # Check if ConnectChain config file exists
    try:
        config_path = settings.get("connectchain.config_path")
        config_file = Path(config_path)
        if config_file.exists():
            print(f"✅ ConnectChain config file exists: {config_path}")
        else:
            print(f"❌ ConnectChain config file not found: {config_path}")
            all_ok = False
    except Exception as e:
        print(f"❌ Could not check ConnectChain config file: {e}")
        all_ok = False

    return all_ok


def test_llm_client_selection():
    """Test that the correct LLM client is selected."""
    print_section("LLM Client Selection")

    use_connectchain = settings.get("llm.use_connectchain", False)
    client = get_llm_client()

    if use_connectchain:
        if "ConnectChain" in client.__class__.__name__:
            print(f"✅ ConnectChain client selected: {client.__class__.__name__}")
            return True
        else:
            print(f"❌ Expected ConnectChain client, got: {client.__class__.__name__}")
            return False
    else:
        if "Azure" in client.__class__.__name__:
            print(f"✅ Azure OpenAI client selected: {client.__class__.__name__}")
            return True
        else:
            print(f"❌ Expected Azure client, got: {client.__class__.__name__}")
            return False


def test_simple_completion():
    """Test a simple chat completion."""
    print_section("Simple Chat Completion Test")

    print("\n🔄 Making a test LLM call...")
    print("   This will verify that ConnectChain can successfully call the LLM.")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say 'Hello from ConnectChain!' and nothing else."},
    ]

    try:
        client = get_llm_client()
        response = client.chat_completion(messages)

        print(f"\n✅ LLM call successful!")
        print(f"Response: {response}")
        return True

    except Exception as e:
        print(f"\n❌ LLM call failed: {e}")
        print("\nPossible issues:")
        print("  - Check your ConnectChain configuration in connectchain.config.yml")
        print("  - Verify AZURE_OPENAI_ENDPOINT is correct")
        print("  - If using EAS, verify CONSUMER_ID and CONSUMER_SECRET")
        print("  - Check network connectivity and proxy settings")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  🧪 CONNECTCHAIN CONFIGURATION TEST")
    print("=" * 70)

    print("\nThis script will verify your ConnectChain setup.\n")

    # Test 1: Configuration
    config_ok = check_configuration()

    if not config_ok:
        print("\n⚠️  Configuration incomplete. Please fix the issues above.")
        print("\nSee CONNECTCHAIN_SETUP.md for setup instructions.")
        return 1

    # Test 2: Client selection
    client_ok = test_llm_client_selection()

    if not client_ok:
        print("\n⚠️  LLM client selection failed.")
        return 1

    # Test 3: Simple completion
    completion_ok = test_simple_completion()

    if not completion_ok:
        print("\n⚠️  LLM call failed. Check the error message above.")
        return 1

    # All tests passed
    print_section("Summary")
    print("\n✅ All tests passed!")
    print("\nYour ConnectChain configuration is working correctly.")
    print("\nYou can now use the Text-to-SQL Agent with ConnectChain:")
    print("""
    from src import Text2SQLAgent

    agent = Text2SQLAgent()
    result = agent.query("Show me top 5 customers by sales")
    print(result["sql"])
    """)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
