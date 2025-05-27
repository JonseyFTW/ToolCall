from flask import Flask, request, jsonify, render_template
from qwen_agent.agents import Assistant
import httpx # Added for custom SSL handling
import logging
import json

app = Flask(__name__)

# --- Configuration ---
LLM_MODEL_NAME = "Qwen3-30B-A3B-FP8"  # IMPORTANT: Update this to your actual model name
VLLM_ENDPOINT_URL = "https://vllm.rangeresources.com/v1/" # This should be the base URL for your vLLM
                                                 # If running Docker on Desktop and vLLM is on host,
                                                 # consider "http://host.docker.internal:PORT/v1/"
                                                 # where PORT is your vLLM's HTTP port.
API_KEY = "123456789" # Updated to match user's working example

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Create a custom httpx client to disable SSL verification
# This is because the user's vLLM server might be using a self-signed certificate
custom_http_client = httpx.Client(verify=False)

# Configure LLM for Qwen-Agent
llm_cfg = {
    "model": LLM_MODEL_NAME,
    "model_server": VLLM_ENDPOINT_URL,
    "api_key": API_KEY,
    "generate_cfg": {
        "top_p": 0.8,
    },
    "http_client": custom_http_client # Pass the custom client to disable SSL verification
                                      # qwen-agent should pass this to the underlying openai.OpenAI client
}
app.logger.info(f"LLM Configuration: {llm_cfg}")
app.logger.info("Note: SSL verification is DISABLED for requests to the LLM model server.")

# Configure Tools
tools_for_assistant = ['code_interpreter']
app.logger.info(f"Tools initialized: {tools_for_assistant}")

# System prompt for the agent
system_prompt = (
    "You are a helpful AI assistant. Your primary goal is to answer the user's questions accurately. "
    "If you don't know the answer, or if the question requires up-to-date information "
    "(e.g., current events, recent data, specific website content), "
    "you MUST use the 'code_interpreter' tool. "
    "To use the 'code_interpreter' for web browsing, you should write and execute Python code "
    "that utilizes the 'playwright' library. For example, to get the content of a webpage, you can "
    "write code like: \n"
    "```python\n"
    "from playwright.sync_api import sync_playwright\n\n"
    "with sync_playwright() as p:\n"
    "    browser = p.chromium.launch()\n"
    "    page = browser.new_page()\n"
    "    page.goto('[https://example.com](https://example.com)')\n"
    "    content = page.content()\n"
    "    print(content) # The print output will be the result of the tool execution\n"
    "    browser.close()\n"
    "```\n"
    "When using the 'code_interpreter' for browsing, be specific with your target URLs or search queries if you need to implement search first. "
    "After retrieving information, synthesize it and present the answer clearly to the user. "
    "If the 'code_interpreter' fails or returns no useful information, state that you couldn't find the information."
)

# Create Assistant Agent
bot = None
try:
    bot = Assistant(
        llm=llm_cfg,
        system_message=system_prompt,
        function_list=tools_for_assistant
    )
    app.logger.info("Assistant agent initialized successfully with code_interpreter.")
except Exception as e:
    app.logger.error(f"Failed to initialize Assistant agent: {e}", exc_info=True)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not bot:
        app.logger.error("Chat request received, but Assistant agent is not initialized.")
        return jsonify({"error": "Agent not initialized. Check backend logs."}), 500

    try:
        data = request.json
        user_query = data.get('query')

        if not user_query:
            return jsonify({"error": "No query provided"}), 400

        app.logger.info(f"Received query: {user_query}")

        current_messages = [{'role': 'user', 'content': user_query}]
        
        final_response_text = ""
        tool_activity_summary = []
        generated_responses = []

        try:
            for response_chunk_list in bot.run(messages=current_messages):
                generated_responses.extend(response_chunk_list)
                for message_part in response_chunk_list:
                    app.logger.debug(f"Agent response part: {message_part}")

                    if message_part.get('role') == 'assistant':
                        content = message_part.get('content', '')
                        if isinstance(content, str):
                            final_response_text += content + " "
                        elif isinstance(content, list):
                            for item in content:
                                if item.get('type') == 'text':
                                    final_response_text += item.get('text', '') + " "
                                
                    elif message_part.get('role') == 'tool_calls':
                        tool_calls_content = message_part.get('content')
                        if isinstance(tool_calls_content, list):
                            for call in tool_calls_content:
                                if call.get('type') == 'tool_code':
                                    tool_name = call.get('tool_name', 'unknown_tool')
                                    tool_args_str = call.get('tool_args', '{}')
                                    tool_activity_summary.append(f"Tool Called: {tool_name} with args (summary): {tool_args_str[:100]}...")
                                    
                    elif message_part.get('role') == 'tool_outputs':
                        tool_outputs_content = message_part.get('content')
                        if isinstance(tool_outputs_content, list):
                            for output_item in tool_outputs_content:
                                tool_name = output_item.get('tool_name', 'unknown_tool_output')
                                output_data = str(output_item.get('output', ''))
                                tool_activity_summary.append(f"Tool '{tool_name}' provided output (summary).")
                                app.logger.info(f"Tool '{tool_name}' raw output (first 300 chars): {output_data[:300]}")

        except Exception as e:
            app.logger.error(f"Error during Assistant agent.run: {e}", exc_info=True)
            # Check for specific httpx connection errors which might still occur if URL is wrong
            if isinstance(e, httpx.ConnectError):
                 return jsonify({"error": f"Connection error communicating with LLM: {e}. Please check VLLM_ENDPOINT_URL and ensure vLLM is running and accessible from Docker."}), 500
            return jsonify({"error": f"Error processing query with agent: {str(e)}"}), 500

        final_response_text = final_response_text.strip()
        if not final_response_text and tool_activity_summary:
            final_response_text = "The agent used tools to process your request. See tool activity for details."
        elif not final_response_text and not tool_activity_summary:
            final_response_text = "I received your query but didn't generate a textual response. Please try rephrasing or check the logs."

        if tool_activity_summary:
            final_response_text += "\n\n[Tool Activity: " + "; ".join(tool_activity_summary) + "]"

        app.logger.info(f"Full agent conversation log for this query (first 5 entries): {generated_responses[:5]}")
        app.logger.info(f"Sending final response to frontend: {final_response_text}")
        return jsonify({"response": final_response_text})

    except Exception as e:
        app.logger.error(f"Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
