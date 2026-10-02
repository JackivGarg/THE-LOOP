"""Explicit offline walkthrough: deterministic sample HTML and simulated rubric.

This uses the real pipeline and deterministic evaluator, but its planner, writer,
and LLM rubric are fixtures. Never describe demo scores as a live model response.
"""
import html
import time

from core.pipeline import PipelineNodes
from utils.deterministic_evaluator import evaluate_html


def sample_html(title: str, description: str, iteration: int) -> str:
    title, description = html.escape(title), html.escape(description)
    responsive = "@media(max-width:700px){.hero,.grid{grid-template-columns:1fr}.hero h1{font-size:42px}nav{flex-wrap:wrap}.wrap{padding:24px}}" if iteration > 0 else ""
    focus = "a:focus-visible{outline:3px solid #dc7a44;outline-offset:5px}" if iteration > 1 else ""
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fbf6ef;color:#292d26;font-family:Georgia,serif}}a{{color:inherit;text-decoration:none}}.wrap{{max-width:1100px;margin:auto;padding:32px 48px}}nav{{display:flex;justify-content:space-between;gap:20px;font:14px Arial}}nav div{{display:flex;gap:24px}}.hero{{display:grid;grid-template-columns:1.3fr 1fr;gap:60px;align-items:center;padding:65px 0}}h1{{font-size:70px;line-height:1.04;letter-spacing:-3px;margin:22px 0}}p{{font:16px/1.8 Arial;color:#62675c}}.tag{{font:11px Arial;letter-spacing:2px;text-transform:uppercase;color:#7c846b}}.button{{display:inline-block;background:#293a2d;color:#fff;padding:16px 22px;border-radius:30px;font:13px Arial}}.art{{height:340px;border-radius:150px 150px 12px 12px;background:linear-gradient(135deg,#d9dfc5,#7f9975);display:flex;align-items:center;justify-content:center;color:#f7f7ec;font-size:170px}}h2{{font-size:35px;font-weight:400}}section{{padding:35px 0}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}article{{padding:25px;border:1px solid #deded0;border-radius:12px}}article h3{{font-size:22px;font-weight:400}}footer{{padding:30px 0;border-top:1px solid #d5d8c9;font:12px Arial}}{responsive}{focus}</style></head>
<body><div class="wrap"><header><nav aria-label="Main navigation"><strong>{title}</strong><div><a href="#about">About</a><a href="#projects">Projects</a><a href="#contact">Contact</a></div></nav></header><main><section class="hero"><div><span class="tag">A thoughtful beginning</span><h1>Made with purpose.<br>Built for people.</h1><p>{description}</p><a class="button" href="#projects">Explore our work ↗</a></div><div class="art" aria-hidden="true">✳</div></section><section id="about"><span class="tag">01 / About</span><h2>Good ideas deserve a considered approach.</h2><p>This is an offline sample used to demonstrate iteration history. Run with Groq to create a website tailored to your full brief.</p></section><section id="projects"><span class="tag">02 / Projects</span><h2>A little care makes all the difference.</h2><div class="grid"><article><h3>Clarity first</h3><p>Find the important story and give it room to breathe.</p></article><article><h3>Better by design</h3><p>Make purposeful decisions, from the first outline to the last detail.</p></article><article><h3>Always evolving</h3><p>Measure what works, learn from feedback, and improve.</p></article></div></section><section id="contact"><span class="tag">03 / Contact</span><h2>Let’s make something meaningful.</h2><p>Replace this sample contact link with your own before publishing.</p><a class="button" href="mailto:hello@example.com">Start a conversation ↗</a></section></main><footer>© {title} · Offline walkthrough sample</footer></div></body></html>'''


def planner(state):
    time.sleep(0.3)
    state["planner_instruction"] = "Offline fixture: establish hierarchy, then add responsive layout and focus states."
    return state


def writer(state):
    time.sleep(0.5)
    state["current_code"] = sample_html(state["user_input"]["title"], state["user_input"]["description"], state["iteration"])
    return state


def evaluator(state):
    time.sleep(0.3)
    report = evaluate_html(state["current_code"], **state["user_input"], check_external_resources=False)
    number = state["iteration"]
    scores = {"layout": min(8, 6 + number), "typography": 7, "responsiveness": min(8, 5 + number * 2), "visual_design": min(8, 6 + number), "description_match": 5}
    rating = {"scores": scores, "deductions": "Simulated rubric: sample copy only partially matches the brief. Live mode uses a model to evaluate actual requirements."}
    state["last_rating_json"] = rating
    state["last_deterministic_evaluation"] = report
    state["last_deductions"] = rating["deductions"]
    state.setdefault("evaluation_history", []).append({"iteration": number + 1, "deterministic": report, "llm_rating": rating})
    return state


DEMO_NODES = PipelineNodes(planner, writer, writer, evaluator)
