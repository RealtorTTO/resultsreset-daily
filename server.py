#!/usr/bin/env python3
"""Results Reset™ Daily — Complete Web Server for Railway
Serves the frontend + handles AI plan generation + sends emails via Gmail SMTP.
"""
import asyncio
import json
import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from anthropic import Anthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ── Logging ──
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resultsreset")

# ── Load system prompt ──
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "teresa_system_prompt.txt")
with open(PROMPT_PATH, "r") as f:
    SYSTEM_PROMPT = f.read()

# ── Config from environment variables ──
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "teresaovercash@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TERESA_EMAIL = os.environ.get("TERESA_NOTIFY_EMAIL", "teresatedder@gmail.com")
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8000
PORT = int(os.environ.get("PORT", 8000))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ════════════════════════════════════════════
# PLAN GENERATION
# ════════════════════════════════════════════

def format_intake_message(data: dict) -> str:
    agent_info = data.get("agentInfo", {})
    parts = ["GENERATE A PERSONALIZED DAILY COACHING PLAN FOR THIS AGENT.\n"]
    parts.append("THIS IS A DAY 1 / FIRST-TIME PLAN — use the intake form answers below.\n")
    parts.append("=" * 60)
    parts.append("\n## AGENT INTAKE FORM ANSWERS\n")
    
    field_map = [
        ("name", "Name"), ("howLong", "Time in real estate"),
        ("goals", "Goals (3/6/12 months)"), ("currentLeadGen", "Current lead gen activities"),
        ("socialMediaSkills", "Social media skills"), ("toolsWanted", "Tools they want most"),
        ("hoursPerWeek", "Hours per week available"), ("culturalBarrier", "Cultural considerations"),
        ("howSoonClosing", "How soon they need a closing"),
        ("buyerConfidence", "Buyer confidence (1-10)"), ("buyerConfidenceWhy", "Why that buyer confidence score"),
        ("sellerConfidence", "Seller confidence (1-10)"), ("sellerConfidenceWhy", "Why that seller confidence score"),
        ("formsKnowledge", "Forms knowledge"), ("givingItYourAll", "Giving it their all (1-5)"),
        ("whyNotHigher", "Why not higher"), ("leadGenComfortable", "Comfortable lead gen"),
        ("leadGenLeastComfortable", "Least comfortable lead gen"),
        ("overwhelming", "Most overwhelming/confusing"), ("personality", "Personality type"),
        ("strengths", "Top strengths"), ("clarityScore", "Daily clarity score (1-10)"),
        ("whereYouAre", "Where they are right now"), ("focusNext60", "Focus for next 30-60 days"),
        ("busyVsProductive", "Busy vs productive answer"),
        ("brutallyHonest", "Brutally honest reason business isn't where they want"),
        ("coachingStyle", "How they like to be coached"), ("offTrack", "What knocks them off track"),
        ("accountabilityGroup", "Willing to join accountability group"),
        ("email", "Email"), ("phone", "Phone"), ("facebook", "Facebook name"),
        ("anythingElse", "Anything else"), ("timeslots", "Available time blocks"),
    ]
    
    for key, label in field_map:
        val = agent_info.get(key, "")
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val) if val else "Not specified"
        if val:
            parts.append(f"**{label}:** {val}")
    
    parts.append("\n" + "=" * 60)
    parts.append("\nIMPORTANT: Return your response as a valid JSON object with this exact structure:")
    parts.append("""
{
  "greeting": "Your personalized Momentum Message opening — 3-5 sentences in Teresa's voice",
  "mirrorMoment": "The Mirror Moment — a reflective prompt based on their answers",
  "eveningReflection": "Evening reflection questions for end of day",
  "tomorrowPrep": "What to prepare tonight for tomorrow",
  "identityStatement": "A personalized I AM identity statement based on their strengths",
  "selfDoubtRebuttal": "A rebuttal to their specific self-doubt, using their own words",
  "schedule": [
    {
      "time": "HH:MM AM/PM",
      "duration": "XX min",
      "category": "mindset|power_block|skill|learn|admin|marketing|current_business|rest",
      "title": "Short descriptive task title",
      "details": "Detailed step-by-step instructions for this task",
      "script": "Copy-paste script text if applicable, or null",
      "motivation": "Teresa's encouraging note for this specific task"
    }
  ]
}

RULES FOR THE SCHEDULE:
- Use their exact available time slots to build the schedule
- Fill EVERY available minute with specific, actionable tasks
- Include at least one Power Block (their most important lead gen time)
- Include copy-paste scripts for conversations, social media, follow-ups
- Include a mindset/identity task at the start of the day
- Include a skill-building task relevant to what they said they need
- Include rest/recharge blocks — you believe in sustainable effort
- Every task must have specific details — never vague instructions
- Adapt intensity based on their confidence level, hours, and situation
- If they said they're broke/urgent, front-load income-producing activities
- If they're burned out, reduce the plan and give permission to do less
- Include 8-15 tasks depending on their available hours
- Time blocks should match their stated availability
""")
    return "\n".join(parts)


def format_checkin_message(data: dict) -> str:
    agent_info = data.get("agentInfo", {})
    checkin = data.get("checkinData", agent_info)
    
    parts = ["GENERATE A PERSONALIZED DAILY COACHING PLAN FOR THIS RETURNING AGENT.\n"]
    parts.append("THIS IS A DAY 2+ PLAN — use the check-in form answers below to adapt their plan.\n")
    parts.append("=" * 60)
    parts.append("\n## CHECK-IN FORM ANSWERS\n")
    
    checkin_fields = [
        ("convoNew", "New conversations since last check-in"),
        ("convoSOI", "SOI/people they know conversations"),
        ("convoTotal", "Total conversations"),
        ("bestConvo", "Most promising conversation"),
        ("win", "Win they want to carry forward"),
        ("didntDo", "What they didn't do and why"),
        ("oneWord", "One word for where they are"),
        ("mental", "Mental/emotional state"),
        ("physical", "Physical energy level"),
        ("personalLife", "Personal life factors"),
        ("activeBuyers", "Active buyers"),
        ("activeListings", "Active/potential listings"),
        ("warmLeads", "Warm leads"),
        ("pending", "Pending/under contract"),
        ("leadAttention", "Lead needing most attention"),
        ("bestTraction", "Activity producing most traction"),
        ("notWorking", "Activity not producing results or avoiding"),
        ("obstacles", "Biggest obstacles"),
        ("obstacleOther", "Specific obstacle"),
        ("lastPlanFelt", "How last plan felt"),
        ("wantMore", "Want MORE of in next plan"),
        ("wantLess", "Want LESS of in next plan"),
        ("skills", "Skills they want help with"),
        ("skillOther", "Specific skill"),
        ("specificRequest", "Specific thing they want in next plan"),
        ("farmArea", "Focus neighborhood/zip for Business Intelligence Brief"),
        ("targetClient", "Type of client/property they want to attract"),
        ("topGoal", "Top goal for this plan period"),
        ("commitment", "Commitment level (1-10)"),
        ("hopingToSee", "Result they're hoping to see"),
        ("stopTelling", "Story they need to stop telling themselves"),
        ("gap", "What's causing the gap between where they are and want to be"),
        ("thrivingVersion", "Version of themselves who is thriving"),
        ("oneThing", "One thing to do differently starting now"),
        ("slots", "Available time blocks"),
    ]
    
    for key, label in checkin_fields:
        val = checkin.get(key, "")
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val) if val else "Not specified"
        if val:
            parts.append(f"**{label}:** {val}")
    
    name = checkin.get("nm", agent_info.get("name", "Agent"))
    email = checkin.get("em", agent_info.get("email", ""))
    parts.insert(3, f"**Agent Name:** {name}")
    if email:
        parts.insert(4, f"**Agent Email:** {email}")
    
    parts.append("\n" + "=" * 60)
    parts.append("\nIMPORTANT: Return your response as a valid JSON object with this exact structure:")
    parts.append("""
{
  "greeting": "Your personalized Momentum Message — reference their check-in answers, celebrate wins, address gaps",
  "mirrorMoment": "The Mirror Moment — use their own words from the gap/thriving questions",
  "eveningReflection": "Evening reflection questions tailored to their day",
  "tomorrowPrep": "What to prepare tonight based on their current pipeline and goals",
  "identityStatement": "A personalized I AM statement that evolves from their check-in",
  "selfDoubtRebuttal": "Counter the specific story they said they need to stop telling themselves",
  "schedule": [
    {
      "time": "HH:MM AM/PM",
      "duration": "XX min",
      "category": "mindset|power_block|skill|learn|admin|marketing|current_business|rest",
      "title": "Short descriptive task title",
      "details": "Detailed step-by-step instructions",
      "script": "Copy-paste script if applicable, or null",
      "motivation": "Teresa's note for this task"
    }
  ]
}

RULES FOR DAY 2+ PLANS:
- Reference their check-in answers directly — quote their words back to them
- If they said the last plan was "too much," simplify this one
- If they said "too easy," push harder with more tasks and higher targets
- If they're discouraged/drained, lead with compassion and reduce the load
- If they're fired up, match their energy with an ambitious plan
- Double down on what they said is producing traction
- Address the activity they're avoiding — name it, give them a script for it
- If they have a specific farm area, include a Business Intelligence section
- Include skills they specifically asked for help with
- Their commitment level should calibrate plan intensity (1-5: gentle, 6-8: standard, 9-10: push hard)
- Use their "win" as fuel — reference it in the greeting
- Use their "story to stop telling" in the self-doubt rebuttal
- Include 8-15 tasks depending on available hours
""")
    return "\n".join(parts)


def build_plan_text_for_email(plan: dict, agent_name: str) -> str:
    lines = []
    lines.append("═" * 50)
    lines.append("RESULTS RESET™ DAILY COACHING PLAN")
    lines.append(f"Agent: {agent_name}")
    lines.append(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    lines.append("═" * 50)
    lines.append("")
    
    if plan.get("greeting"):
        lines.extend(["💛 MOMENTUM MESSAGE", "─" * 30, plan["greeting"], ""])
    if plan.get("identityStatement"):
        lines.extend(["🪞 IDENTITY STATEMENT", "─" * 30, plan["identityStatement"], ""])
    if plan.get("selfDoubtRebuttal"):
        lines.extend(["💪 SELF-DOUBT REBUTTAL", "─" * 30, plan["selfDoubtRebuttal"], ""])
    
    cat_labels = {
        "mindset": "✨ MINDSET", "power_block": "⚡ POWER BLOCK",
        "skill": "📚 SKILL BUILD", "learn": "🎓 YOUR LESSON",
        "admin": "📋 ADMIN", "marketing": "📱 MARKETING",
        "current_business": "💼 CURRENT BIZ", "rest": "☕ RECHARGE",
    }
    
    if plan.get("schedule"):
        lines.extend(["📅 YOUR DAILY SCHEDULE", "─" * 30])
        for task in plan["schedule"]:
            cat = cat_labels.get(task.get("category", "admin"), "📋 TASK")
            lines.append(f"\n⏰ {task.get('time', '')} ({task.get('duration', '')})")
            lines.append(f"   {cat}: {task.get('title', '')}")
            lines.append(f"   {task.get('details', '')}")
            if task.get("script") and task["script"] != "null":
                lines.append(f"\n   📋 SCRIPT:")
                for sline in task["script"].split("\n"):
                    lines.append(f"   {sline}")
            if task.get("motivation"):
                lines.append(f"\n   💛 {task['motivation']}")
        lines.append("")
    
    if plan.get("mirrorMoment"):
        lines.extend(["🪞 MIRROR MOMENT", "─" * 30, plan["mirrorMoment"], ""])
    if plan.get("eveningReflection"):
        lines.extend(["🌙 EVENING REFLECTION", "─" * 30, plan["eveningReflection"], ""])
    if plan.get("tomorrowPrep"):
        lines.extend(["📝 TOMORROW PREP", "─" * 30, plan["tomorrowPrep"], ""])
    
    lines.extend(["═" * 50, "Results Reset™ Daily — resultsresetcoaching.com",
                   "Created by Teresa Overcash · Top 1% Producer · NCREC Instructor"])
    return "\n".join(lines)


# ════════════════════════════════════════════
# EMAIL (Gmail SMTP)
# ════════════════════════════════════════════

def send_email_smtp(to_address: str, subject: str, body: str):
    """Send an email via Gmail SMTP."""
    if not GMAIL_APP_PASSWORD:
        logger.warning("[EMAIL] No GMAIL_APP_PASSWORD set — skipping email send")
        return
    
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        logger.info(f"[EMAIL] Sent to {to_address}: {subject}")
    except Exception as e:
        logger.error(f"[EMAIL ERROR] Failed to send to {to_address}: {e}")


async def send_plan_to_teresa(agent_name: str, agent_email: str, plan_text: str, is_checkin: bool):
    plan_type = "Check-In" if is_checkin else "New Agent"
    subject = f"[Results Reset] {plan_type} Plan Generated — {agent_name} ({agent_email})"
    body = f"A new coaching plan was just generated.\n\n"
    body += f"Agent: {agent_name}\nEmail: {agent_email}\nType: {plan_type}\n"
    body += f"Time: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
    body += "─" * 50 + "\n\n" + plan_text
    
    await asyncio.to_thread(send_email_smtp, TERESA_EMAIL, subject, body)


async def schedule_followup(agent_name: str, agent_email: str):
    try:
        await asyncio.sleep(24 * 60 * 60)  # 24 hours
        subject = "It's me Teresa Overcash checking in on you and your action plan!"
        body = f"Hey {agent_name},\n\n"
        body += "Just checking in on you! How did your plan go? Do you have any questions for me?\n\n"
        body += "If you're ready to set up your next day, click the link below to get your next plan:\n\n"
        body += "Get another daily plan ($5): https://teresa300.gumroad.com/l/resultsresetday2\n\n"
        body += "Or if you want to lock in unlimited daily plans:\n"
        body += "Monthly plan: https://teresa300.gumroad.com/l/resultsresetmonthly\n"
        body += "Annual plan: https://teresa300.gumroad.com/l/resultsresetannual\n\n"
        body += "Reply to this email anytime — I read every single one.\n\n"
        body += "I'm in your corner. Always.\n\n"
        body += "— Teresa\n\nTeresa Overcash\nTop 1% Producer | NCREC Licensed Instructor\n"
        body += "Realty ONE Group Results | Winston-Salem, NC\nQuestions? teresaovercash@gmail.com"
        
        await asyncio.to_thread(send_email_smtp, agent_email, subject, body)
        logger.info(f"[FOLLOWUP] 24hr follow-up sent to {agent_name} at {agent_email}")
    except asyncio.CancelledError:
        logger.info(f"[FOLLOWUP] Cancelled for {agent_name}")
    except Exception as e:
        logger.error(f"[FOLLOWUP ERROR] {agent_name}: {e}")


# ════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════

@app.post("/api/generate")
async def generate_plan(request: Request):
    try:
        data = await request.json()
        is_checkin = data.get("isCheckin", False)
        agent_info = data.get("agentInfo", {})
        agent_name = agent_info.get("name", "Agent")
        agent_email = agent_info.get("email", "")
        
        if is_checkin:
            user_message = format_checkin_message(data)
        else:
            user_message = format_intake_message(data)
        
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        
        plan_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                plan_text += block.text
        
        clean = plan_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        
        plan = json.loads(clean)
        
        if agent_name and agent_email:
            plan_email_text = build_plan_text_for_email(plan, agent_name)
            asyncio.create_task(send_plan_to_teresa(agent_name, agent_email, plan_email_text, is_checkin))
            asyncio.create_task(schedule_followup(agent_name, agent_email))
        
        return JSONResponse(content={"content": [{"text": json.dumps(plan)}]})
    
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=422, content={"error": f"Plan format invalid: {str(e)}"})
    except Exception as e:
        logger.error(f"[API ERROR] {e}")
        return JSONResponse(status_code=422, content={"error": f"Plan generation failed: {str(e)}"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": MODEL}


# ════════════════════════════════════════════
# SERVE FRONTEND (static files)
# ════════════════════════════════════════════

# Serve static directory for any extra assets
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve index.html for all non-API routes (SPA-style)
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(html_path, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
