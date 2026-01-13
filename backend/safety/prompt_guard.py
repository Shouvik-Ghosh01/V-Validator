from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

PROMPT_GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"


def is_prompt_safe(text: str) -> bool:
    """
    Returns True if prompt is SAFE, False if it is an injection/jailbreak attempt.
    Fail-open by default.
    """

    try:
        response = client.chat.completions.create(
            model=PROMPT_GUARD_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a security classifier.\n"
                        "Classify the user input strictly as one of:\n"
                        "SAFE\n"
                        "UNSAFE\n\n"
                        "Rules:\n"
                        "- Output ONLY one word\n"
                        "- No explanation\n"
                        "- No punctuation\n"
                        "- No additional text"
                    )
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0,
            max_tokens=3,
        )

        verdict = response.choices[0].message.content.strip().upper()

        return verdict == "SAFE"

    except Exception:
        # Fail-open: never block users if guard fails
        return True
