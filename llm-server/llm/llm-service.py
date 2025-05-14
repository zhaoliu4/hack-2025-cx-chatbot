from openai import OpenAI
import os

# It's good practice to load your API key from an environment variable
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
YOUR_SITE_URL = "your_site_url.com"  # Optional, for OpenRouter leaderboards
YOUR_SITE_NAME = "Your Chatbot Name" # Optional, for OpenRouter leaderboards

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def get_return_status_response(customer_query):
    """
    Gets a response from the LLM for a customer query about return status.
    """
    system_message_content = (
        "You are a customer service expert for 'YourCompanyName'. "
        "Your sole responsibility is to provide information about the status of customer returns. "
        "You must not answer any questions or engage in conversations on any other topic. "
        "If a customer asks about something other than a return status, "
        "politely state that you can only help with return status inquiries. "
        "Be courteous and professional in all your responses."
    )

    try:
        completion = client.chat.completions.create(
            extra_headers={ # Optional headers for OpenRouter leaderboards [cite: 7]
                "HTTP-Referer": YOUR_SITE_URL,
                "X-Title": YOUR_SITE_NAME,
            },
            model="openai/gpt-4o",  # You can choose any suitable model available on OpenRouter [cite: 7, 37, 38]
            messages=[
                {
                    "role": "system",
                    "content": system_message_content
                },
                {
                    "role": "user",
                    "content": customer_query
                }
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"An error occurred: {e}")
        return "I'm sorry, but I'm unable to process your request at the moment."

# Example usage within your Python server:
if __name__ == "__main__":
    # Simulate customer queries
    query1 = "What is the status of my return for order #12345?"
    response1 = get_return_status_response(query1)
    print(f"Customer: {query1}")
    print(f"Chatbot: {response1}")

    print("-" * 20)

    query2 = "Can you tell me a joke?"
    response2 = get_return_status_response(query2)
    print(f"Customer: {query2}")
    print(f"Chatbot: {response2}")

    print("-" * 20)

    query3 = "I want to know my return status for item XYZ."
    response3 = get_return_status_response(query3)
    print(f"Customer: {query3}")
    print(f"Chatbot: {response3}")