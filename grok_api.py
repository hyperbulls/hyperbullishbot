import aiohttp
from config import XAI_API_KEY, GROK_CONTENT_FILE, DISCORD_MAX_MESSAGE_LENGTH

async def query_grok(prompt: str, market_and_news_data: str, tesla_posts: str) -> str:
    if not XAI_API_KEY:
        return "Error: xAI API key is not configured. Please contact the bot administrator."
    
    try:
        with open(GROK_CONTENT_FILE, "r") as f:
            static_system_prompt = f.read().strip()
        print(f"[DEBUG] Loaded system prompt from {GROK_CONTENT_FILE}, length: {len(static_system_prompt)} characters")
    except FileNotFoundError:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: File not found")
        return f"Error: {GROK_CONTENT_FILE} not found. Please create it with the system prompt."
    except IOError as e:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: {str(e)}")
        return f"Error: Failed to read {GROK_CONTENT_FILE} - {str(e)}"

    # Construct enhanced system prompt with fetched data
    enhanced_system_prompt = (
        f"{static_system_prompt}\n\n"
        f"Use the following TSLA, earnings, market, news, and timestamp data in your analysis:\n"
        f"{market_and_news_data}\n\n"
        f"{tesla_posts}"
    )
    
    # Log the full prompt
    full_prompt = (
        f"[DEBUG] Full prompt sent to Grok API:\n"
        f"System Prompt:\n{enhanced_system_prompt}\n\n"
        f"User Query:\n{prompt}"
    )
    print(full_prompt)
    
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    timeout = aiohttp.ClientTimeout(total=20)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    print(f"[DEBUG] API request attempt {attempt + 1}, status: {response.status}")
                    if response.status == 200:
                        result = await response.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "No response received from Grok.")
                        print(f"[DEBUG] Grok response length: {len(content)} characters")
                        if len(content) > DISCORD_MAX_MESSAGE_LENGTH:
                            content = content[:DISCORD_MAX_MESSAGE_LENGTH - 50] + "... (truncated due to length)"
                        return content
                    else:
                        error_body = await response.text()
                        return f"Error: API request failed with status {response.status}: {response.reason}\nHeaders: {response.headers}\nBody: {error_body[:1000]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"[ERROR] API request attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            continue
        except Exception as e:
            print(f"[ERROR] Unexpected error in API request: {type(e).__name__}: {str(e)}")
            return f"Error: Failed to connect to Grok API - {str(e)}"
    return "Error: Failed to connect to Grok API after 3 attempts."
