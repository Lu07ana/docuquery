import json
import time

from google import genai
from google.genai import types

from retrieval import connect_db, retrieve


# =========================================================
# SETUP
# =========================================================

client = genai.Client()

conn = connect_db()

# =========================================================
# LOAD 10 GENERATION TEST QUESTIONS
# =========================================================

with open(
    "generation_questions_10.json",
    "r",
    encoding="utf-8"
) as file:

    test_questions = json.load(file)

# =========================================================
# BUILD CONTEXT
# =========================================================

def build_context(results):

    parts = []

    for (
        text,
        source,
        pages,
        score
    ) in results:

        parts.append(
            f"""
Source: {source}
Pages: {pages}

{text}
"""
        )

    return "\n\n".join(parts)


# =========================================================
# ASK GEMINI
# =========================================================

def ask_gemini(question, results):

    context = build_context(
        results
    )

    prompt = f"""
Answer the question using ONLY the provided context.

Give a short and direct answer.

Do not use outside knowledge.

If the answer cannot be found in the context, say:
"I could not find enough information in the provided documents."

CONTEXT:

{context}

QUESTION:

{question}

ANSWER:
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            candidate_count=1,
            max_output_tokens=500,
            seed=42,
            thinking_config=types.ThinkingConfig(
                thinking_level="low"
            )

        )
    )

    return response.text


# =========================================================
# RESULTS
# =========================================================

top3_correct = 0
top5_correct = 0

top3_better = 0
top5_better = 0
equal = 0

comparison_results = []


# =========================================================
# RUN 10 QUESTIONS
# =========================================================

for number, test in enumerate(
    test_questions,
    start=1
):

    question = test["question"]

    expected_answer = test[
        "expected_answer"
    ]


    print()
    print(
        "=" * 70
    )

    print(
        f"QUESTION {number}/10"
    )

    print(
        "=" * 70
    )

    print()
    print(
        question
    )


    # -----------------------------------------------------
    # Retrieve ONCE
    #
    # Top 3 is simply the first three of the top 5.
    # -----------------------------------------------------

    results_5 = retrieve(
        conn,
        question,
        top_k=5
    )

    results_3 = results_5[:3]


    # -----------------------------------------------------
    # GEMINI WITH TOP 3
    # -----------------------------------------------------

    try:

        answer_3 = ask_gemini(
            question,
            results_3
        )

    except Exception as error:

        print(
            "\nGemini error for TOP 3:"
        )

        print(
            error
        )

        answer_3 = "ERROR"


    # Small pause between API requests
    time.sleep(1)


    # -----------------------------------------------------
    # GEMINI WITH TOP 5
    # -----------------------------------------------------

    try:

        answer_5 = ask_gemini(
            question,
            results_5
        )

    except Exception as error:

        print(
            "\nGemini error for TOP 5:"
        )

        print(
            error
        )

        answer_5 = "ERROR"


    # -----------------------------------------------------
    # SHOW RESULTS
    # -----------------------------------------------------

    print()
    print(
        "EXPECTED ANSWER:"
    )

    print(
        expected_answer
    )


    print()
    print(
        "GEMINI — TOP 3 CHUNKS:"
    )

    print(
        answer_3
    )


    print()
    print(
        "GEMINI — TOP 5 CHUNKS:"
    )

    print(
        answer_5
    )


    # -----------------------------------------------------
    # MANUAL CORRECTNESS
    # -----------------------------------------------------

    print()
    print(
        "Compare each answer with the expected answer."
    )


    while True:

        score_3 = input(
            "Is TOP 3 correct? (y/n): "
        ).strip().lower()

        if score_3 in {
            "y",
            "n"
        }:
            break


    while True:

        score_5 = input(
            "Is TOP 5 correct? (y/n): "
        ).strip().lower()

        if score_5 in {
            "y",
            "n"
        }:
            break


    if score_3 == "y":
        top3_correct += 1

    if score_5 == "y":
        top5_correct += 1


    # -----------------------------------------------------
    # WHICH ANSWER IS BETTER?
    # -----------------------------------------------------

    while True:

        preference = input(
            "Which answer is better? "
            "(3 / 5 / equal): "
        ).strip().lower()

        if preference in {
            "3",
            "5",
            "equal"
        }:
            break


    if preference == "3":

        top3_better += 1

    elif preference == "5":

        top5_better += 1

    else:

        equal += 1


    # -----------------------------------------------------
    # STORE RESULT
    # -----------------------------------------------------

    comparison_results.append(
        {
            "question": question,
            "expected_answer": expected_answer,
            "top3_answer": answer_3,
            "top5_answer": answer_5,
            "top3_correct": (
                score_3 == "y"
            ),
            "top5_correct": (
                score_5 == "y"
            ),
            "preferred": preference
        }
    )


    # Pause before next question
    time.sleep(1)


# =========================================================
# FINAL RESULTS
# =========================================================

print()
print(
    "=" * 70
)

print(
    "GENERATION COMPARISON"
)

print(
    "=" * 70
)


print()

print(
    "TOP 3 correct:",
    top3_correct,
    "/ 10"
)

print(
    "TOP 5 correct:",
    top5_correct,
    "/ 10"
)


print()

print(
    "TOP 3 preferred:",
    top3_better
)

print(
    "TOP 5 preferred:",
    top5_better
)

print(
    "Equal:",
    equal
)


# =========================================================
# SAVE RESULTS
# =========================================================

with open(
    "generation_comparison_results.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        comparison_results,
        file,
        indent=2,
        ensure_ascii=False
    )


print()
print(
    "Detailed results saved to:"
)

print(
    "generation_comparison_results.json"
)


# =========================================================
# CLOSE DATABASE
# =========================================================

conn.close()