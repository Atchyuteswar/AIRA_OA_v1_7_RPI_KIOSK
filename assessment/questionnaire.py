from __future__ import annotations

# AIRA-OA custom symptom profile. This is a research-prototype index, not a
# validated clinical questionnaire or diagnostic score.
QUESTIONS = [
    {"id": "pain_location", "domain": "context", "question": "Where is the main area of pain or discomfort today?", "options": [("Right knee", 0), ("Left knee", 0), ("Both knees", 0), ("Hip / other / none", 0)]},
    {"id": "pain_rest", "domain": "pain", "question": "How much pain is present at rest right now?", "options": [("0 - No pain", 0), ("1-3 - Mild", 1), ("4-6 - Moderate", 2), ("7-10 - Severe", 3)]},
    {"id": "pain_movement", "domain": "pain", "question": "How much pain occurs during movement or walking?", "options": [("0 - No pain", 0), ("1-3 - Mild", 1), ("4-6 - Moderate", 2), ("7-10 - Severe", 3)]},
    {"id": "stiffness", "domain": "stiffness", "question": "How often does joint stiffness affect daily activity?", "options": [("Never", 0), ("Occasionally", 1), ("Frequently", 2), ("Daily", 3)]},
    {"id": "morning_stiffness", "domain": "stiffness", "question": "If morning stiffness occurs, how long does it usually last?", "options": [("None / <5 min", 0), ("5–15 min", 1), ("15–30 min", 2), (">30 min", 3)]},
    {"id": "chair_rise", "domain": "function", "question": "How difficult is it to rise from a standard chair?", "options": [("No difficulty", 0), ("Mild", 1), ("Moderate", 2), ("Severe / unable", 3)]},
    {"id": "stairs", "domain": "function", "question": "How difficult is climbing stairs?", "options": [("No difficulty", 0), ("Mild", 1), ("Moderate", 2), ("Severe / unable", 3)]},
    {"id": "walking", "domain": "function", "question": "How much does pain/stiffness limit continuous walking?", "options": [("No limitation", 0), ("Short limitation", 1), ("Moderate limitation", 2), ("Severe limitation", 3)]},
    {"id": "standing", "domain": "function", "question": "How difficult is prolonged standing?", "options": [("No difficulty", 0), ("Mild", 1), ("Moderate", 2), ("Severe", 3)]},
    {"id": "instability", "domain": "instability", "question": "How often does the participant feel joint instability while walking?", "options": [("Never", 0), ("Rarely", 1), ("Sometimes", 2), ("Frequently", 3)]},
    {"id": "activity_avoidance", "domain": "activity_limitation", "question": "How often are activities avoided because of pain or stiffness?", "options": [("Never", 0), ("Rarely", 1), ("Sometimes", 2), ("Frequently", 3)]},
    {"id": "swelling", "domain": "swelling", "question": "How often is visible or perceived joint swelling reported?", "options": [("Never", 0), ("Occasionally", 1), ("Frequently", 2), ("Currently present", 3)]},
    {"id": "previous_assessment", "domain": "context", "question": "Has the participant previously received an OA-related clinical assessment?", "options": [("No", 0), ("Unknown", 0), ("Yes", 1), ("Yes + previous imaging/treatment", 2)]},
]

DOMAIN_LABELS = {
    "pain": "Pain",
    "stiffness": "Stiffness",
    "function": "Functional difficulty",
    "instability": "Instability",
    "activity_limitation": "Activity limitation",
    "swelling": "Swelling",
}


class Questionnaire:
    def __init__(self):
        self.reset()

    def reset(self):
        self.answers = []
        self.index = 0

    @property
    def current_question(self):
        if self.index >= len(QUESTIONS):
            return None
        return QUESTIONS[self.index]

    def answer(self, option_number):
        question = self.current_question
        if question is None or option_number not in (1, 2, 3, 4):
            return False
        label, score = question["options"][option_number - 1]
        self.answers.append({
            "id": question["id"],
            "domain": question.get("domain", "context"),
            "question": question["question"],
            "answer": label,
            "score": score,
        })
        self.index += 1
        return True

    def undo(self):
        """Step back one question (v1.3 could only discard everything)."""
        if not self.answers:
            return False
        self.answers.pop()
        self.index -= 1
        return True

    def complete(self):
        return self.index >= len(QUESTIONS)

    def finish(self):
        # Only symptom domains contribute to the custom research index.
        # Location and previous-assessment history are contextual, not severity points.
        domains = {name: {"label": label, "score": 0, "max_score": 0} for name, label in DOMAIN_LABELS.items()}
        for question in QUESTIONS:
            domain = question.get("domain")
            if domain not in domains:
                continue
            domains[domain]["max_score"] += max(score for _, score in question["options"])
        for answer in self.answers:
            domain = answer.get("domain")
            if domain in domains:
                domains[domain]["score"] += int(answer.get("score", 0))

        score = sum(item["score"] for item in domains.values())
        max_score = sum(item["max_score"] for item in domains.values())
        return {
            "answers": self.answers,
            "score": score,
            "max_score": max_score,
            "score_label": "Custom AIRA-OA symptom burden index",
            "score_type": "research_prototype_non_validated",
            "complete": self.complete(),
            "domains": domains,
            "context": {
                "pain_location": next((a["answer"] for a in self.answers if a["id"] == "pain_location"), "-"),
                "previous_assessment": next((a["answer"] for a in self.answers if a["id"] == "previous_assessment"), "-"),
            },
            "disclaimer": "Custom research-prototype index; not a validated clinical scale and not a diagnostic result.",
        }
