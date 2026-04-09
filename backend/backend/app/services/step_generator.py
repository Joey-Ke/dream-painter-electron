import requests
import json

class StepGenerator:

    def __init__(self):
        self.api_key = "sk-53ceb332c7384525a2235c0cbb62d5ba"
        self.url = "https://api.siliconflow.cn/v1/chat/completions"

    def generate_steps(self, subject: str, step_count: int = 8):
        print("API KEY:", self.api_key)
        prompt = f"""
请生成黑白简笔画风格的“{subject}”卡通图片，并且将这个简笔画拆分成几个步骤，并且声称每一步的教学图片。

要求：
1. 每一步非常简单
2. 一共{step_count}步
3. 输出JSON数组
"""

        response = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "messages": [{"role": "user", "content": prompt}],
            }
        )

        text = response.json()["choices"][0]["message"]["content"]

        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])

