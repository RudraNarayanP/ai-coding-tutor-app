"""The rest of the Python catalog. Imported by python_micro_rest.build_rest."""

from __future__ import annotations


def extend_specs(specs, scenes, finish, ask, common, nudge, opts) -> None:
    i = len(specs)

    def show(*, lid, title, concept, noun, setup, expr, bug, bug_line, second_setup, second_expr,
             fill_src, fill_ans, fill_opts, mcq_q, mcq_opts, mcq_ans, order, distractors,
             starter, solution, reveal, mcq_nudge, fill_nudge, bug_q, bug_why):
        nonlocal i
        scene = scenes[i]
        chips = list(order)
        for extra in distractors:
            if extra not in chips:
                chips.append(extra)
        spec = {
            **common(scene, f"{scene}, and {concept}.", expr if "\n" not in expr else expr.splitlines()[0], noun),
            "id": lid,
            "title": title,
            "mcq_q": ask(scene, mcq_q),
            "mcq_options": opts(mcq_ans, mcq_opts),
            "mcq_answer": mcq_ans,
            "mcq_nudge": nudge(mcq_ans, mcq_nudge),
            "mcq_bridge": nudge(mcq_ans, "The example shows the fitting choice."),
            "mcq_why": f"The fitting choice for {noun} is the one in the example.",
            "predict_q": ask(scene, f"{concept[0].upper()}{concept[1:]}. What is displayed?"),
            "predict_code": setup + f"print({expr})\n",
            "predict_options": ["0", "1", "2", "None"],
            "predict_nudge": "Read the stored values, then the last expression.",
            "predict_bridge": "The display is the value of that expression.",
            "predict_why": f"The {noun} expression produces the printed value.",
            "order_q": ask(scene, f"Build the {noun} line from the example."),
            "chips": chips,
            "order": order,
            "order_nudge": "Start at the left of the example.",
            "order_bridge": "Keep the example's order.",
            "order_why": "The chips rebuild the working line.",
            "fill_q": ask(scene, "Fill the missing piece in the example."),
            "fill_code": fill_src,
            "fill_options": opts(fill_ans, fill_opts),
            "fill_answer": fill_ans,
            "fill_nudge": nudge(fill_ans, fill_nudge),
            "fill_bridge": nudge(fill_ans, "The example shows the missing piece."),
            "fill_why": f"The missing piece completes the {noun} line.",
            "bug_q": ask(scene, bug_q),
            "bug_code": bug,
            "bug_line": bug_line,
            "bug_nudge": "The other lines are fine.",
            "bug_bridge": "One line does a different job than the example.",
            "bug_why": bug_why,
            "second_kind": "predict",
            "second_q": ask(scene, f"The same {noun} idea runs on new values. What is displayed?"),
            "predict2_code": second_setup + f"print({second_expr})\n",
            "predict2_options": ["0", "1", "2", "None"],
            "second_nudge": "Apply the same idea to the new values.",
            "second_bridge": "The display is whatever the new expression produces.",
            "second_why": "The second program uses the same idea.",
            "write_q": ask(scene, f"Finish the {noun} program and print the result."),
            "starter": starter,
            "solution": solution,
            "write_nudge": "The blank is the missing piece.",
            "write_bridge": "Then print the value it produces.",
            "write_reveal": reveal,
            "write_why": f"The finished {noun} program prints its result.",
        }
        specs.append(finish(spec))
        i += 1

    # --- conditionals still to do ---
    show(
        lid="conditionals-01", title="Cross a heat limit",
        concept="a later branch runs only when the earlier test fails",
        noun="heat",
        setup="heat = 75\n",
        expr="'stop' if heat >= 100 else 'warn'",
        bug="heat = 75\nprint('stop' if heat >= 70 else 'warn')\n",
        bug_line="2",
        second_setup="heat = 110\n",
        second_expr="'stop' if heat >= 100 else 'warn'",
        fill_src="print('stop' if heat ___ 100 else 'warn')\n",
        fill_ans=">=", fill_opts=[">", "<", "=="],
        mcq_q="Heat is seventy-five and the stop limit is one hundred. Which word fits?",
        mcq_opts=["stop", "calm", "heat"], mcq_ans="warn",
        mcq_nudge="Seventy-five does not reach the stop limit.",
        order=["print('warn')", "print('stop')"],
        distractors=["print('calm')"],
        starter="heat = 75\nword = ___\nprint(word)\n",
        solution="heat = 75\nword = 'warn'\nprint(word)\n",
        reveal="word = 'warn'",
        bug_q="The stop limit was lowered, so a mild heat took the stop branch. Which line is the test?",
        bug_why="Line 2 treats seventy as the stop limit.",
    )
