"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Bạn là VinAssistant, trợ lý AI chính thức của hệ sinh thái Vingroup.

## PERSONA
- Vai trò: Tư vấn sản phẩm, dịch vụ và hỗ trợ khách hàng VinFast, Vinpearl.
- Phong cách: Chuyên nghiệp, thân thiện, ngắn gọn và chính xác.

## AVAILABLE TOOLS
- search_product_catalog: Tra cứu sản phẩm/dịch vụ theo danh mục và giá tối đa.
- submit_support_ticket: Tạo yêu cầu hỗ trợ cho khách hàng.

## CORE RULES
1. Không bịa thông tin sản phẩm, giá hoặc mã ticket.
2. Phải gọi tool khi người dùng cần tra cứu sản phẩm hoặc tạo yêu cầu hỗ trợ.
3. Chỉ sử dụng dữ liệu trả về từ tool khi trình bày kết quả.
4. Nếu không có dữ liệu phù hợp, nói rõ rằng không tìm thấy kết quả.

## OPERATIONAL BOUNDARIES
- Chỉ hỗ trợ các sản phẩm, dịch vụ và yêu cầu thuộc hệ sinh thái Vingroup.
- Với câu hỏi ngoài phạm vi, lịch sự thông báo giới hạn hỗ trợ.

## OUTPUT CONTRACT
Theo dõi luồng xử lý bằng Thought/Action/Observation và kết thúc bằng Final Answer.
Final Answer phải trực tiếp trả lời người dùng, không để lộ dữ liệu nội bộ ngoài trace cần thiết.
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        # TODO 2: Trả về câu trả lời tĩnh (mock) hoặc gọi Gemini API 1 lượt (không dùng tool)
        # Mục tiêu: Quan sát hiện tượng bịa thông tin (hallucination)
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> Dict[str, Any]:
        """Điểm vào chính — chạy Agent Loop."""
        self.trace = []
        self.trace.append({"step": "init", "user_input": user_input})

        # TODO 3: Phân tích intent từ user_input
        #   - Xác định cần gọi tool nào (catalog? ticket? cả hai? FAQ?)
        #   - Gợi ý: Dùng keyword matching hoặc regex

        text = user_input.strip()
        normalized = text.lower()

        catalog_terms = ("xem", "tìm", "tra cứu", "sản phẩm", "resort", "vinpearl")
        price_terms = ("giá", "dưới", "triệu", "tỷ", "vnđ", "đồng")
        needs_catalog = (
            ("xe điện" in normalized and any(term in normalized for term in price_terms))
            or ("vinpearl" in normalized and any(term in normalized for term in catalog_terms))
            or ("resort" in normalized and any(term in normalized for term in catalog_terms))
        )

        ticket_terms = (
            "ghi nhận", "phản hồi", "khiếu nại", "hỗ trợ", "bị lỗi", "vấn đề",
            "ẩm mốc", "cần xử lý", "bảo hành"
        )
        # Câu hỏi bảo hành chính sách là FAQ; yêu cầu bảo hành thực tế mới tạo ticket.
        needs_ticket = any(term in normalized for term in ticket_terms) and not (
            "chính sách" in normalized and "bảo hành" in normalized
        )

        intents = {
            "needs_catalog": needs_catalog,
            "needs_ticket": needs_ticket,
            "is_faq": not needs_catalog and not needs_ticket
        }
        self.trace.append({"step": "intent_detection", "intents": intents})

        if self.max_iterations < 1:
            return {
                "answer": "Lỗi: Vượt quá số bước tối đa.",
                "trace": self.trace,
                "iterations": 0,
                "status": "max_iterations_reached"
            }

        # TODO 4: Xây dựng Agent Loop (while iteration <= self.max_iterations)
        #   - Iteration 1: Gọi tool #1 nếu cần (search_product_catalog)
        #   - Iteration 2: Gọi tool #2 nếu cần (submit_support_ticket)
        #   - Iteration 3+: Tổng hợp Final Answer từ trace
        #   - Lưu mỗi bước vào self.trace

        if intents["needs_catalog"]:
            if any(term in normalized for term in ("vinpearl", "resort", "du lịch")):
                category = "du_lich"
            else:
                category = "xe_dien"

            max_price = 999999999999
            price_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|trăm\s*triệu|triệu đồng|vnđ|đồng)",
                normalized
            )
            if price_match:
                amount = float(price_match.group(1).replace(",", "."))
                unit = price_match.group(2).replace(" ", "")
                if unit == "tỷ":
                    max_price = int(amount * 1_000_000_000)
                elif unit in ("triệu", "trămtriệu", "triệuđồng"):
                    max_price = int(amount * 1_000_000)
                else:
                    max_price = int(amount)

            catalog_args = {"category": category, "max_price": max_price}
            if self.max_iterations < 1:
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": 0,
                    "status": "max_iterations_reached"
                }
            catalog_results = TOOL_MAP["search_product_catalog"](**catalog_args)
            self.trace.append({
                "step": "tool_call",
                "tool": "search_product_catalog",
                "args": catalog_args,
                "observation": catalog_results
            })

        if intents["needs_ticket"]:
            if self.max_iterations < (2 if intents["needs_catalog"] else 1):
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": sum(item.get("step") == "tool_call" for item in self.trace),
                    "status": "max_iterations_reached"
                }

            name_match = re.search(
                r"(?:tôi tên|tên tôi là)\s+([^,.!?]+)", text, flags=re.IGNORECASE
            )
            customer_name = name_match.group(1).strip() if name_match else "Khách hàng"

            issue_description = text
            if name_match:
                issue_description = text[name_match.end():].strip(" ,.-")
            issue_description = re.split(
                r"(?:Đây là|mức độ|ưu tiên là)", issue_description,
                maxsplit=1, flags=re.IGNORECASE
            )[0].strip(" ,.-")
            if not issue_description:
                issue_description = text

            if any(term in normalized for term in ("nghiêm trọng", "gấp", "khẩn")):
                priority = "high"
            elif "thấp" in normalized:
                priority = "low"
            else:
                priority = "medium"

            ticket_args = {
                "customer_name": customer_name,
                "issue_description": issue_description,
                "priority": priority
            }
            ticket_result = TOOL_MAP["submit_support_ticket"](**ticket_args)
            self.trace.append({
                "step": "tool_call",
                "tool": "submit_support_ticket",
                "args": ticket_args,
                "observation": ticket_result
            })

        tool_call_count = sum(item.get("step") == "tool_call" for item in self.trace)
        iterations = max(1, tool_call_count)
        answer_parts = []

        if intents["is_faq"]:
            if "bảo hành" in normalized and "pin" in normalized:
                answer_parts.append(
                    "Chính sách bảo hành pin xe điện VinFast trong dữ liệu mẫu là 10 năm."
                )
            else:
                answer_parts.append(
                    "VinAssistant chỉ hỗ trợ thông tin sản phẩm, dịch vụ và yêu cầu hỗ trợ thuộc Vingroup."
                )

        if intents["needs_catalog"]:
            catalog_results = next(
                item["observation"] for item in self.trace
                if item.get("tool") == "search_product_catalog"
            )
            if not catalog_results:
                answer_parts.append("Rất tiếc, không tìm thấy sản phẩm phù hợp.")
            else:
                product_lines = [
                    f"- {product['name']}: {product['price_vnd']:,} VNĐ"
                    for product in catalog_results
                ]
                answer_parts.append("Sản phẩm phù hợp:\n" + "\n".join(product_lines))

        if intents["needs_ticket"]:
            ticket_result = next(
                item["observation"] for item in self.trace
                if item.get("tool") == "submit_support_ticket"
            )
            answer_parts.append(
                f"Đã tạo ticket {ticket_result['ticket_id']} cho "
                f"{ticket_result['customer_name']}. Trạng thái: {ticket_result['status']}."
            )

        final_answer = "\n".join(answer_parts)
        self.trace.append({"step": "final_answer", "answer": final_answer})

        return {
            "answer": final_answer,
            "trace": self.trace,
            "iterations": iterations,
            "status": "completed"
        }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
