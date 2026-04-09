import os
import json
from http import HTTPStatus
import dashscope
from dashscope import Generation

# 直接在这里填你的 API Key（sk-xxxx）
dashscope.api_key = "sk-53ceb332c7384525a2235c0cbb62d5ba"

def generate_drawing_steps(prompt, subject):
    system_prompt = """
You are an art teacher.
Break drawing into simple step-by-step instructions.
Return JSON with steps.
"""

    user_prompt = f"""
Teach how to draw {subject}.
Prompt: {prompt}
Return 5 drawing steps.
"""

    response = Generation.call(
        model='qwen-flash',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        result_format='json'
    )

    if response.status_code == HTTPStatus.OK:
        return response.output.choices[0].message.content
    else:
        raise Exception(f"调用失败：{response.code} - {response.message}")

# 测试一下
if __name__ == "__main__":
    try:
        res = generate_drawing_steps("simple style", "cat")
        print(res)
    except Exception as e:
        print("错误:", e)
