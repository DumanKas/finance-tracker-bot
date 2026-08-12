import os
import aiohttp
import asyncio

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"


async def analyze_finances(
    user_id: int,
    period_title: str,
    total: int,
    category_stats: list,
) -> str:

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        return (
            "⚠️ <b>DeepSeek пока не настроен.</b>\n\n"
            "Добавь переменную <code>DEEPSEEK_API_KEY</code> "
            "в переменные окружения Railway."
        )

    categories_text = "\n".join(
        f"- {category}: {amount} ₸"
        for category, amount in category_stats
    )

    system_prompt = """
Ты — финансовый аналитик личного финансового бота.

Твоя задача — анализировать расходы пользователя
и давать короткие, понятные и практичные выводы.

Правила:
- Не придумывай отсутствующие данные.
- Не меняй суммы.
- Не выполняй математические расчёты, если они не нужны.
- Не осуждай пользователя за его расходы.
- Не давай инвестиционных или кредитных рекомендаций.
- Пиши на русском языке.
- Используй понятное форматирование.
- Ответ должен быть компактным: примерно 5-10 пунктов.
"""

    user_prompt = f"""
Проанализируй расходы пользователя.

Период: {period_title}
Общая сумма: {total} ₸

Расходы по категориям:
{categories_text}

Сделай:
1. Краткий вывод.
2. Назови 1-2 самые крупные категории.
3. Укажи, на что стоит обратить внимание.
4. Дай 2 практических совета по контролю расходов.
"""

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "stream": False,
        "max_tokens": 800,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
            ) as response:

                if response.status != 200:
                    error_text = await response.text()

                    print(
                        f"DeepSeek API error "
                        f"{response.status}: {error_text}"
                    )

                    return (
                        "❌ Не удалось получить анализ "
                        "от ИИ.\n\n"
                        f"Код ошибки: {response.status}"
                    )

                data = await response.json()

                return data["choices"][0]["message"]["content"]

    except asyncio.TimeoutError:
        return "⏳ DeepSeek слишком долго отвечает. Попробуй ещё раз."

    except Exception as e:
        print(f"DeepSeek error: {e}")
        return "❌ Произошла ошибка при обращении к ИИ."