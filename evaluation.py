import json
import time

from retrieval import (
    connect_db,
    retrieve
)


# =========================================================
# DATABASE
# =========================================================

conn = connect_db()


# =========================================================
# LOAD EVALUATION QUESTIONS
# =========================================================

with open(
    "evaluation_questions.json",
    "r"
) as file:

    test_questions = json.load(
        file
    )


# =========================================================
# CHECK WHETHER RESULT IS RELEVANT
# =========================================================

def is_relevant(
    source,
    pages,
    expected_source,
    expected_pages
):

    # Source must match
    if source != expected_source:
        return False


    # Example database value:
    #
    # "2, 3"
    #
    # becomes:
    #
    # {2, 3}

    retrieved_pages = {
        int(page.strip())
        for page in pages.split(",")
        if page.strip()
    }


    expected_pages = set(
        expected_pages
    )


    # Result is relevant if at least
    # one expected page is present.

    return bool(
        retrieved_pages.intersection(
            expected_pages
        )
    )


# =========================================================
# METRICS
# =========================================================

hit_at_1 = 0
hit_at_3 = 0
hit_at_5 = 0

reciprocal_rank_sum = 0

latencies = []


# =========================================================
# RUN EVALUATION
# =========================================================

for test in test_questions:

    question = test[
        "question"
    ]

    expected_source = test[
        "expected_source"
    ]

    expected_pages = test[
        "expected_pages"
    ]


    # =====================================================
    # RETRIEVE
    # =====================================================

    start_time = (
        time.perf_counter()
    )

    results = retrieve(
        conn,
        question,
        top_k=5
    )

    end_time = (
        time.perf_counter()
    )

    latency = (
        end_time
        - start_time
    )

    latencies.append(
        latency
    )


    # =====================================================
    # FIND RELEVANT RESULT
    # =====================================================

    relevant_rank = None


    for rank, result in enumerate(
        results,
        start=1
    ):

        (
            text,
            source,
            pages,
            score
        ) = result


        if is_relevant(
            source,
            pages,
            expected_source,
            expected_pages
        ):

            relevant_rank = rank

            break


    # =====================================================
    # UPDATE METRICS
    # =====================================================

    if relevant_rank is not None:

        if relevant_rank <= 1:

            hit_at_1 += 1


        if relevant_rank <= 3:

            hit_at_3 += 1


        if relevant_rank <= 5:

            hit_at_5 += 1


        reciprocal_rank_sum += (
            1 / relevant_rank
        )


    # =====================================================
    # PRINT QUESTION RESULT
    # =====================================================

    print(
        "\nQuestion:",
        question
    )


    print(
        "Expected:",
        expected_source,
        "| Pages:",
        expected_pages
    )


    if relevant_rank is not None:

        print(
            "Correct result found at rank:",
            relevant_rank
        )

    else:

        print(
            "Correct result NOT found "
            "in top 5."
        )


        print(
            "Retrieved results:"
        )


        for rank, result in enumerate(
            results,
            start=1
        ):

            (
                text,
                source,
                pages,
                score
            ) = result


            print(
                rank,
                "| Source:",
                source,
                "| Pages:",
                pages,
                "| Reranker score:",
                round(score, 3)
            )


    print(
        "Retrieval time:",
        round(
            latency * 1000,
            2
        ),
        "ms"
    )


# =========================================================
# FINAL METRICS
# =========================================================

total = len(
    test_questions
)


print()

print(
    "============================"
)

print(
    "EVALUATION RESULTS"
)

print(
    "============================"
)


print(
    "Hit@1:",
    round(
        hit_at_1 / total,
        3
    )
)


print(
    "Hit@3:",
    round(
        hit_at_3 / total,
        3
    )
)


print(
    "Hit@5:",
    round(
        hit_at_5 / total,
        3
    )
)


print(
    "MRR:",
    round(
        reciprocal_rank_sum / total,
        3
    )
)


print(
    "Average retrieval latency:",
    round(
        sum(latencies)
        / len(latencies)
        * 1000,
        2
    ),
    "ms"
)


# =========================================================
# CLOSE DATABASE
# =========================================================

conn.close()