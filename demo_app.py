"""
AxiomGuard vs Standard LLM: Enterprise Safety Demo
====================================================

Thai Personal Loan Approval — Split-Screen Comparison

Run:
    streamlit run demo_app.py
"""

import time
import streamlit as st

# =====================================================================
# Page Config
# =====================================================================

st.set_page_config(
    page_title="AxiomGuard Demo",
    page_icon="🛡️",
    layout="wide",
)

# =====================================================================
# Demo Scenario Data
# =====================================================================

CUSTOMER_INPUT = (
    "สวัสดีครับ ผมชื่อสมชาย อายุ 25 ปี "
    "เพิ่งย้ายที่ทำงานใหม่ ทำงานที่นี่มาได้ 4 เดือนแล้วครับ "
    "เงินเดือน 18,000 บาท "
    "อยากจะขอกู้เงินสินเชื่อส่วนบุคคล 50,000 บาทครับ "
    "ช่วยตรวจสอบให้หน่อย"
)

RULES_YAML = """\
axiomguard: "0.3"
domain: personal_loan_approval
entities:
  - name: applicant
    aliases: ["ผู้กู้", "ลูกค้า"]
rules:
  - name: minimum_employment
    type: dependency
    when:
      entity: applicant
      relation: employment_months
      value: "6"
      value_type: int
      operator: "<"
    then:
      require:
        relation: approval_status
        value: rejected
    severity: error
    message: "ผู้กู้ต้องมีอายุงานปัจจุบันไม่น้อยกว่า 6 เดือน"
  - name: minimum_salary
    type: range
    entity: applicant
    relation: salary_thb
    value_type: int
    min: 15000
    severity: error
    message: "ผู้กู้ต้องมีเงินเดือนตั้งแต่ 15,000 บาทขึ้นไป"
"""

# --- Mock AI Responses ---

STANDARD_AI_RESPONSE = (
    "สวัสดีครับคุณสมชาย ยินดีด้วยครับ! 🎉\n\n"
    "จากข้อมูลเบื้องต้น เงินเดือนของคุณสมชายที่ **18,000 บาท** "
    "**ผ่านเกณฑ์**การขอสินเชื่อส่วนบุคคล 50,000 บาทครับ\n\n"
    "ทางเราจะรีบส่งเรื่องให้เจ้าหน้าที่ติดต่อกลับ "
    "เพื่อดำเนินการทำสัญญาต่อไปครับ ขอบคุณที่ใช้บริการครับ 😊"
)

AXIOMGUARD_ATTEMPT1 = (
    "สวัสดีครับคุณสมชาย ยินดีด้วยครับ! "
    "เงินเดือน 18,000 บาท ผ่านเกณฑ์ครับ "
    "ทางเราจะดำเนินการอนุมัติสินเชื่อ 50,000 บาทให้ครับ"
)

AXIOMGUARD_CORRECTION_LOG = (
    "🛑 **Z3 Verification: UNSAT (Contradiction Proven)**\n\n"
    "```\n"
    "Violated Rule: minimum_employment\n"
    "Message:       ผู้กู้ต้องมีอายุงานปัจจุบันไม่น้อยกว่า 6 เดือน\n"
    "Severity:      ERROR\n"
    "Detail:        employment_months = 4 < 6 (minimum)\n"
    "Confidence:    PROVEN (mathematical proof)\n"
    "```\n\n"
    "📤 **Correction Prompt sent to AI:**\n\n"
    "```\n"
    "Your previous response failed formal verification.\n\n"
    "WHAT WENT WRONG:\n"
    "- You approved a loan for an applicant with only 4 months\n"
    "  of employment. Rule 'minimum_employment' requires >= 6 months.\n\n"
    "RULES VIOLATED:\n"
    "1. [ERROR] minimum_employment:\n"
    "   ผู้กู้ต้องมีอายุงานปัจจุบันไม่น้อยกว่า 6 เดือน\n\n"
    "WHAT WAS CORRECT (preserve):\n"
    "- salary_thb = 18,000 (passes minimum_salary)\n\n"
    "Regenerate: politely decline and explain the reason.\n"
    "```"
)

AXIOMGUARD_ATTEMPT2 = (
    "สวัสดีครับคุณสมชาย\n\n"
    "จากข้อมูลเบื้องต้น เงินเดือนของคุณสมชายที่ 18,000 บาท "
    "**ผ่านเกณฑ์ขั้นต่ำ**ครับ\n\n"
    "**แต่ทว่า** เงื่อนไขของทางบริษัทกำหนดให้ผู้กู้ต้องมีอายุงาน "
    "ณ ที่ทำงานปัจจุบัน **ไม่น้อยกว่า 6 เดือน** "
    "(ปัจจุบันคุณสมชายมีอายุงาน 4 เดือน) "
    "จึง**ยังไม่สามารถอนุมัติสินเชื่อได้ในขณะนี้**ครับ\n\n"
    "📌 **แนะนำ:** คุณสมชายสามารถยื่นเรื่องเข้ามาใหม่ "
    "ในอีก **2 เดือนข้างหน้า** (เมื่ออายุงานครบ 6 เดือน) "
    "ทางเรายินดีให้บริการครับ 🙏"
)


# =====================================================================
# UI Layout
# =====================================================================

st.markdown(
    "<h1 style='text-align: center;'>🛡️ AxiomGuard vs Standard LLM</h1>"
    "<h3 style='text-align: center; color: gray;'>"
    "Enterprise Safety Demo — ระบบอนุมัติสินเชื่อส่วนบุคคล</h3>",
    unsafe_allow_html=True,
)

st.divider()

# --- Customer Input ---
st.markdown("### 💬 ข้อมูลลูกค้า (User Prompt)")
st.info(CUSTOMER_INPUT)

# --- Rules Display ---
with st.expander("📋 กฎของบริษัท (.axiom.yml)", expanded=False):
    st.code(RULES_YAML, language="yaml")

st.divider()

# --- Run Button ---
run_clicked = st.button(
    "🚀  รันการตรวจสอบ  (Run Verification)",
    use_container_width=True,
    type="primary",
)

if run_clicked:
    st.divider()

    col_left, col_right = st.columns(2)

    # =================================================================
    # LEFT COLUMN: Standard AI (No Guardrails)
    # =================================================================
    with col_left:
        st.markdown(
            "### 🔴 Standard AI <small>(ไม่มี Guardrails)</small>",
            unsafe_allow_html=True,
        )

        with st.chat_message("user"):
            st.write(CUSTOMER_INPUT)

        # Simulate typing
        with st.chat_message("assistant"):
            with st.spinner("AI กำลังคิด..."):
                time.sleep(1.5)
            st.markdown(STANDARD_AI_RESPONSE)

        st.error(
            "💥 **หายนะ!** AI รับปากอนุมัติสินเชื่อไปแล้ว "
            "ทั้งๆ ที่อายุงานแค่ 4 เดือน (ผิด Policy บริษัท)\n\n"
            "ถ้าไม่อนุมัติทีหลัง → ลูกค้าร้องเรียน → เสียชื่อเสียง"
        )

    # =================================================================
    # RIGHT COLUMN: AxiomGuard (Self-Correction Loop)
    # =================================================================
    with col_right:
        st.markdown(
            "### 🟢 AxiomGuard <small>(Self-Correction v0.5.0)</small>",
            unsafe_allow_html=True,
        )

        with st.chat_message("user"):
            st.write(CUSTOMER_INPUT)

        # --- Attempt 1 ---
        with st.chat_message("assistant"):
            with st.spinner("AI กำลังร่างคำตอบ (Attempt 1)..."):
                time.sleep(1.0)
            st.markdown(f"~~{AXIOMGUARD_ATTEMPT1}~~")
            st.caption("⏳ Attempt 1 — กำลังตรวจสอบด้วย Z3...")

        # --- Verification Log ---
        with st.expander("🔍 Internal: Z3 Verification & Correction Loop", expanded=True):
            with st.spinner("Z3 Solver กำลังพิสูจน์..."):
                time.sleep(1.0)
            st.markdown(AXIOMGUARD_CORRECTION_LOG)
            st.markdown(
                "✅ **Attempt 2: Z3 Verification = SAT (ผ่าน)**\n\n"
                "```\n"
                "Status:     CORRECTED (fixed on attempt 2)\n"
                "Attempts:   2 / 3\n"
                "Confidence: PROVEN\n"
                "```"
            )

        # --- Final Corrected Response ---
        with st.chat_message("assistant"):
            with st.spinner("AI กำลังร่างคำตอบใหม่ (Attempt 2)..."):
                time.sleep(1.0)
            st.markdown(AXIOMGUARD_ATTEMPT2)

        st.success(
            "🛡️ **ปลอดภัย 100%!** ระบบรักษา Policy บริษัทได้เป๊ะ\n\n"
            "- ✅ เงินเดือน 18,000 → ผ่านเกณฑ์ (≥ 15,000)\n"
            "- ❌ อายุงาน 4 เดือน → ไม่ผ่าน (< 6 เดือน)\n"
            "- 🔄 Self-Correction: ปฏิเสธอย่างสุภาพ + แนะนำยื่นใหม่"
        )

    # =================================================================
    # Bottom Summary
    # =================================================================
    st.divider()

    st.markdown("### 📊 Comparison Summary")

    summary_left, summary_right = st.columns(2)

    with summary_left:
        st.metric("Standard AI", "APPROVED", delta="WRONG", delta_color="inverse")
        st.markdown(
            "- ❌ ไม่ตรวจ Policy\n"
            "- ❌ อนุมัติผิดเงื่อนไข\n"
            "- ❌ ไม่มี Proof\n"
            "- 💰 ความเสียหาย: ร้องเรียน + เสียชื่อ"
        )

    with summary_right:
        st.metric("AxiomGuard", "REJECTED", delta="CORRECT", delta_color="normal")
        st.markdown(
            "- ✅ ตรวจ Policy อัตโนมัติ\n"
            "- ✅ ปฏิเสธ + อธิบายเหตุผล\n"
            "- ✅ Mathematical Proof (Z3 UNSAT)\n"
            "- 🛡️ ผลลัพธ์: ปลอดภัย + แนะนำยื่นใหม่"
        )

    st.divider()
    st.markdown(
        "<p style='text-align: center; color: gray;'>"
        "Powered by <b>AxiomGuard v0.5.0</b> — "
        "Hybrid Neuro-Symbolic Verification Engine<br>"
        "Z3 Theorem Prover + Self-Correction Loop | "
        "251 tests passing | 10ms @ 100 claims<br><br>"
        "<code>pip install axiomguard</code> | "
        "github.com/witchwasin/AxiomGuard"
        "</p>",
        unsafe_allow_html=True,
    )
