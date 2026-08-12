import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

OPENMODEL_API_URL = "https://api.openmodel.ai/v1/messages"
OPENMODEL_MODEL = "deepseek-v4-flash"


async def analyze_finances(
    user_id: int,
    period_title: str,
    total: int,
    category_stats: list,
) -> str:

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        return (
            "⚠️ <b>OpenModel пока не настроен.</b>\n\n"
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
        "model": OPENMODEL_MODEL,
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": (
                    system_prompt
                    + "\n\n"
                    + user_prompt
                ),
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                OPENMODEL_API_URL,
                headers=headers,
                json=payload,
            ) as response:

                response_text = await response.text()

                if response.status != 200:
                    print(
                        f"OpenModel API error "
                        f"{response.status}: "
                        f"{response_text}"
                    )

                    return (
                        "❌ Не удалось получить анализ от ИИ.\n\n"
                        f"Код ошибки: {response.status}"
                    )

                data = await response.json()

                try:
                    return data["content"][0]["text"]

                except (KeyError, IndexError, TypeError):
                    print(
                        f"Неожиданный ответ OpenModel: {data}"
                    )

                    return (
                        "❌ ИИ вернул неожиданный формат ответа."
                    )

    except asyncio.TimeoutError:
        return (
            "⏳ OpenModel слишком долго отвечает. "
            "Попробуй ещё раз."
        )

    except Exception as e:
        print(f"OpenModel error: {e}")

        return (
            "❌ Произошла ошибка при обращении к ИИ."
        )