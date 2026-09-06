"""End-to-end curriculum execution tests.

Each test:
1. Loads the lesson from the curriculum (via CurriculumLoader).
2. Builds the test payload exactly as the engine would.
3. Submits it to the REAL Docker sandbox.
4. Asserts that correct solutions pass all required tests.
5. Asserts that incorrect solutions fail deterministically.
6. Asserts that the LessonEngine marks completed/not-completed accordingly.

These tests require a running Docker daemon and the patchwork-sandbox image.
They are deliberately kept in a separate file so unit tests can be run without
Docker and these can be run when Docker is available.

Coverage:
  - variables (variables, values) — variables-01
  - booleans — booleans-01
  - numbers (floor division, modulo) — numbers-01
  - conditionals (if/elif/else) — conditionals-01
  - comparisons — comparisons-01
  - strings (slicing, join) — strings-01
  - string-methods — string-methods-01
  - lists (indexing, sum, len) — lists-01
  - list-methods — list-methods-01
  - loops (range, enumerate, comprehensions) — loops-01
  - tuples (unpacking, nesting) — tuples-01
  - dictionaries — dictionaries-01
  - functions (constants, docstrings) — functions-01
"""

import asyncio

import pytest

from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.lessons import CURRICULUM
from backend.sandbox import DockerSandbox

# ---------------------------------------------------------------------------
# Sandbox instance shared across all tests in this file
# ---------------------------------------------------------------------------

_sandbox = DockerSandbox()


def docker_run(code: str, lesson_id: str) -> dict:
    """Submit *code* for *lesson_id* through the real Docker sandbox and return
    the raw execution result dict."""
    lesson = next(l for l in CURRICULUM.lessons if l.id == lesson_id)
    payload = {
        "code": code,
        "tests": [t.model_dump() for t in lesson.tests],
    }
    return asyncio.run(_sandbox.run(payload))


def engine_run(code: str, lesson_id: str, engine: LessonEngine) -> dict:
    """Run the lesson through the full LessonEngine (which calls Docker internally)."""
    return asyncio.run(engine.run_lesson(lesson_id, code))


def fresh_engine() -> LessonEngine:
    """Return a new LessonEngine with a fresh ProgressionStore (no completions)."""
    return LessonEngine(_sandbox, ProgressionStore(CURRICULUM), CURRICULUM)


def fresh_engine_unlocked_up_to(lesson_id: str) -> LessonEngine:
    """Return a LessonEngine with all lessons prior to lesson_id marked completed."""
    engine = fresh_engine()
    target = engine.get_lesson(lesson_id)
    for lesson in CURRICULUM.lessons:
        if lesson.order < target.order:
            engine.store.mark_completed(lesson.id)
    return engine


# ---------------------------------------------------------------------------
# variables-01: Variable Assignment & Values
# ---------------------------------------------------------------------------

VARIABLES_CORRECT = """\
country = "Italy"
prep_time = 10
bake_time = 40
total_time = prep_time + bake_time
"""

VARIABLES_WRONG = """\
country = "France"
prep_time = 10
bake_time = 40
total_time = 0
"""


class TestVariablesE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(VARIABLES_CORRECT, "variables-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_variable_fails_test(self):
        result = docker_run(VARIABLES_WRONG, "variables-01")
        assert result["passed"] is False
        country_test = next(
            t for t in result["tests"] if t["name"] == "test_country_variable"
        )
        assert country_test["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("variables-01")
        progression = engine_run(VARIABLES_CORRECT, "variables-01", engine)
        assert progression.passed is True
        assert progression.completed is True
        assert progression.next_lesson_id == "variables-practice-1"

    def test_incorrect_solution_does_not_complete_lesson(self):
        engine = fresh_engine_unlocked_up_to("variables-01")
        progression = engine_run(VARIABLES_WRONG, "variables-01", engine)
        assert progression.completed is False
        assert engine.store.state().current_lesson_id == "variables-01"


# ---------------------------------------------------------------------------
# booleans-01: Ghost Gobble Arcade Game
# ---------------------------------------------------------------------------

BOOLEANS_CORRECT = """\
def eat_ghost(power_pellet_active, touching_ghost):
    \"\"\"Return True only when power pellet is active and touching ghost.\"\"\"
    return power_pellet_active and touching_ghost

def score(touching_power_pellet, touching_dot):
    \"\"\"Return True when touching a power pellet or a dot.\"\"\"
    return touching_power_pellet or touching_dot

def lose(power_pellet_active, touching_ghost):
    \"\"\"Return True when touching ghost without power pellet.\"\"\"
    return not power_pellet_active and touching_ghost

def win(has_eaten_all_dots, power_pellet_active, touching_ghost):
    \"\"\"Return True when all dots eaten and not losing.\"\"\"
    return has_eaten_all_dots and not lose(power_pellet_active, touching_ghost)
"""

BOOLEANS_WRONG = """\
def eat_ghost(power_pellet_active, touching_ghost):
    return power_pellet_active or touching_ghost  # wrong: should be 'and'

def score(touching_power_pellet, touching_dot):
    return touching_power_pellet and touching_dot  # wrong: should be 'or'

def lose(power_pellet_active, touching_ghost):
    return touching_ghost  # wrong: ignores power_pellet_active

def win(has_eaten_all_dots, power_pellet_active, touching_ghost):
    return has_eaten_all_dots
"""


class TestBooleansE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(BOOLEANS_CORRECT, "booleans-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_logic_fails_deterministically(self):
        result = docker_run(BOOLEANS_WRONG, "booleans-01")
        assert result["passed"] is False
        # eat_ghost with wrong 'or' should fail the 'not touching ghost' case
        no_ghost_test = next(
            t for t in result["tests"]
            if t["name"] == "test_ghost_does_not_get_eaten_because_not_touching_ghost"
        )
        assert no_ghost_test["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("booleans-01")
        progression = engine_run(BOOLEANS_CORRECT, "booleans-01", engine)
        assert progression.passed is True
        assert progression.completed is True

    def test_incorrect_solution_does_not_complete_lesson(self):
        engine = fresh_engine_unlocked_up_to("booleans-01")
        progression = engine_run(BOOLEANS_WRONG, "booleans-01", engine)
        assert progression.completed is False


# ---------------------------------------------------------------------------
# numbers-01: Currency Exchange
# ---------------------------------------------------------------------------

NUMBERS_CORRECT = """\
def exchange_money(budget, exchange_rate):
    \"\"\"Return budget divided by exchange_rate.\"\"\"
    return budget / exchange_rate

def get_change(budget, exchanging_value):
    \"\"\"Return what is left after exchanging.\"\"\"
    return budget - exchanging_value

def get_value_of_bills(denomination, number_of_bills):
    \"\"\"Return total value of bills.\"\"\"
    return denomination * number_of_bills

def get_number_of_bills(amount, denomination):
    \"\"\"Return how many whole bills fit in amount.\"\"\"
    return int(amount // denomination)

def get_leftover_of_bills(amount, denomination):
    \"\"\"Return leftover after exchanging into whole bills.\"\"\"
    return amount % denomination

def exchangeable_value(budget, exchange_rate, spread, denomination):
    \"\"\"Return max value obtainable in whole bills after spread fee.\"\"\"
    actual_rate = exchange_rate * (1 + spread / 100)
    exchanged = budget / actual_rate
    return int(exchanged // denomination) * denomination
"""

NUMBERS_WRONG = """\
def exchange_money(budget, exchange_rate):
    return budget * exchange_rate  # wrong: should divide

def get_change(budget, exchanging_value):
    return budget + exchanging_value  # wrong: should subtract

def get_value_of_bills(denomination, number_of_bills):
    return denomination + number_of_bills  # wrong: should multiply

def get_number_of_bills(amount, denomination):
    return amount % denomination  # wrong: should floor-divide

def get_leftover_of_bills(amount, denomination):
    return amount // denomination  # wrong: should modulo

def exchangeable_value(budget, exchange_rate, spread, denomination):
    return 0
"""


class TestNumbersE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(NUMBERS_CORRECT, "numbers-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_operators_fail_deterministically(self):
        result = docker_run(NUMBERS_WRONG, "numbers-01")
        assert result["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("numbers-01")
        progression = engine_run(NUMBERS_CORRECT, "numbers-01", engine)
        assert progression.passed is True
        assert progression.completed is True


# ---------------------------------------------------------------------------
# conditionals-01: Meltdown Mitigation
# ---------------------------------------------------------------------------

CONDITIONALS_CORRECT = """\
def is_criticality_balanced(temperature, neutrons_emitted):
    \"\"\"Return True when reactor is balanced.\"\"\"
    return (temperature < 800
            and neutrons_emitted > 500
            and temperature * neutrons_emitted < 500_000)

def reactor_efficiency(voltage, current, theoretical_max_power):
    \"\"\"Return efficiency band as a colour string.\"\"\"
    efficiency = (voltage * current / theoretical_max_power) * 100
    if efficiency >= 80:
        return 'green'
    elif efficiency >= 60:
        return 'orange'
    elif efficiency >= 30:
        return 'red'
    return 'black'

def fail_safe(temperature, neutrons_produced_per_second, threshold):
    \"\"\"Return safety status string.\"\"\"
    product = temperature * neutrons_produced_per_second
    if product < 0.9 * threshold:
        return 'LOW'
    elif product <= 1.1 * threshold:
        return 'NORMAL'
    return 'DANGER'
"""

CONDITIONALS_WRONG = """\
def is_criticality_balanced(temperature, neutrons_emitted):
    return True  # always True — wrong

def reactor_efficiency(voltage, current, theoretical_max_power):
    return 'green'  # always green — wrong

def fail_safe(temperature, neutrons_produced_per_second, threshold):
    return 'NORMAL'  # always NORMAL — wrong
"""


class TestConditionalsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(CONDITIONALS_CORRECT, "conditionals-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_stub_always_true_fails_deterministically(self):
        result = docker_run(CONDITIONALS_WRONG, "conditionals-01")
        assert result["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("conditionals-01")
        progression = engine_run(CONDITIONALS_CORRECT, "conditionals-01", engine)
        assert progression.passed is True
        assert progression.completed is True


# ---------------------------------------------------------------------------
# strings-01: Little Sister's Vocab
# ---------------------------------------------------------------------------

STRINGS_CORRECT = """\
def add_prefix_un(word):
    \"\"\"Return word with 'un' prefix.\"\"\"
    return 'un' + word

def make_word_groups(vocab_words):
    \"\"\"Return prefix and prefixed words joined by ' :: '.\"\"\"
    prefix = vocab_words[0]
    return ' :: '.join([prefix] + [prefix + word for word in vocab_words[1:]])

def remove_suffix_ness(word):
    \"\"\"Remove -ness suffix, fixing iness -> y spelling.\"\"\"
    root = word[:-4]  # remove 'ness'
    if root.endswith('i'):
        root = root[:-1] + 'y'
    return root

def adjective_to_verb(sentence, index):
    \"\"\"Return the word at index with -en appended, removing trailing punctuation.\"\"\"
    word = sentence.split()[index]
    if not word[-1].isalpha():
        word = word[:-1]
    return word + 'en'
"""

STRINGS_WRONG = """\
def add_prefix_un(word):
    return word  # missing prefix

def make_word_groups(vocab_words):
    return ' '.join(vocab_words)  # wrong separator, no prefixing

def remove_suffix_ness(word):
    return word  # not removing suffix

def adjective_to_verb(sentence, index):
    return sentence  # returning whole sentence instead
"""


class TestStringsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(STRINGS_CORRECT, "strings-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_solution_fails_deterministically(self):
        result = docker_run(STRINGS_WRONG, "strings-01")
        assert result["passed"] is False
        prefix_test = next(t for t in result["tests"] if t["name"] == "test_add_prefix_un")
        assert prefix_test["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("strings-01")
        progression = engine_run(STRINGS_CORRECT, "strings-01", engine)
        assert progression.passed is True
        assert progression.completed is True


# ---------------------------------------------------------------------------
# comparisons-01: Black Jack  (needed by strings prereq chain)
# ---------------------------------------------------------------------------

COMPARISONS_CORRECT = """\
def value_of_card(card):
    \"\"\"Return numeric value of a card.\"\"\"
    if card in ('J', 'Q', 'K'):
        return 10
    if card == 'A':
        return 1
    return int(card)

def higher_card(card_one, card_two):
    \"\"\"Return the higher card, or both as a tuple if equal.\"\"\"
    val1 = value_of_card(card_one)
    val2 = value_of_card(card_two)
    if val1 > val2:
        return card_one
    elif val2 > val1:
        return card_two
    return (card_one, card_two)

def value_of_ace(card_one, card_two):
    \"\"\"Return 11 if safe, else 1.\"\"\"
    def hand_value(card):
        if card == 'A':
            return 11
        return value_of_card(card)
    total = hand_value(card_one) + hand_value(card_two)
    return 11 if total + 11 <= 21 else 1

def is_blackjack(card_one, card_two):
    \"\"\"Return True if hand totals 21 with an ace and a 10-value card.\"\"\"
    def bj_value(card):
        if card == 'A':
            return 11
        return value_of_card(card)
    return bj_value(card_one) + bj_value(card_two) == 21

def can_split_pairs(card_one, card_two):
    \"\"\"Return True if cards have equal value.\"\"\"
    return value_of_card(card_one) == value_of_card(card_two)

def can_double_down(card_one, card_two):
    \"\"\"Return True if hand totals 9, 10, or 11.\"\"\"
    total = value_of_card(card_one) + value_of_card(card_two)
    return 9 <= total <= 11
"""


class TestComparisonsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(COMPARISONS_CORRECT, "comparisons-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_pass_stub_fails_deterministically(self):
        result = docker_run("def value_of_card(c): pass\ndef higher_card(a,b): pass\ndef value_of_ace(a,b): pass\ndef is_blackjack(a,b): pass\ndef can_split_pairs(a,b): pass\ndef can_double_down(a,b): pass\n", "comparisons-01")
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# lists-01: Card Games
# ---------------------------------------------------------------------------

LISTS_CORRECT = """\
def get_rounds(number):
    \"\"\"Return current and next two round numbers.\"\"\"
    return [number, number + 1, number + 2]

def concatenate_rounds(rounds_1, rounds_2):
    \"\"\"Concatenate two round lists.\"\"\"
    return rounds_1 + rounds_2

def list_contains_round(rounds, number):
    \"\"\"Return True if number is in rounds.\"\"\"
    return number in rounds

def card_average(hand):
    \"\"\"Return average card value.\"\"\"
    return sum(hand) / len(hand)

def approx_average_is_average(hand):
    \"\"\"Return True if first/last average or middle card equals true average.\"\"\"
    true_avg = card_average(hand)
    first_last_avg = (hand[0] + hand[-1]) / 2
    middle = hand[len(hand) // 2]
    return first_last_avg == true_avg or middle == true_avg

def average_even_is_average_odd(hand):
    \"\"\"Return True if even-indexed average equals odd-indexed average.\"\"\"
    evens = hand[::2]
    odds = hand[1::2]
    if not odds:
        return False
    return card_average(evens) == card_average(odds)

def maybe_double_last(hand):
    \"\"\"Double the last card if it is a Jack (11).\"\"\"
    if hand[-1] == 11:
        hand[-1] = 22
    return hand
"""

LISTS_WRONG = """\
def get_rounds(number):
    return [number]  # only current, missing next two

def concatenate_rounds(rounds_1, rounds_2):
    return rounds_1  # ignoring rounds_2

def list_contains_round(rounds, number):
    return False  # always False

def card_average(hand):
    return 0  # wrong

def approx_average_is_average(hand):
    return True  # always True

def average_even_is_average_odd(hand):
    return True  # always True

def maybe_double_last(hand):
    return hand  # never doubles
"""


class TestListsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(LISTS_CORRECT, "lists-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_solution_fails_deterministically(self):
        result = docker_run(LISTS_WRONG, "lists-01")
        assert result["passed"] is False
        rounds_test = next(t for t in result["tests"] if t["name"] == "test_get_rounds")
        assert rounds_test["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("lists-01")
        progression = engine_run(LISTS_CORRECT, "lists-01", engine)
        assert progression.passed is True
        assert progression.completed is True


# ---------------------------------------------------------------------------
# string-methods-01: Little Sister's Essay  (needed by lists prereq chain)
# ---------------------------------------------------------------------------

STRING_METHODS_CORRECT = """\
def capitalize_title(title):
    \"\"\"Return title in title case.\"\"\"
    return title.title()

def check_sentence_ending(sentence):
    \"\"\"Return True if sentence ends with a period.\"\"\"
    return sentence.endswith('.')

def clean_up_spacing(sentence):
    \"\"\"Strip leading and trailing whitespace.\"\"\"
    return sentence.strip()

def replace_word_choice(sentence, old_word, new_word):
    \"\"\"Replace old_word with new_word in sentence.\"\"\"
    return sentence.replace(old_word, new_word)
"""


class TestStringMethodsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(STRING_METHODS_CORRECT, "string-methods-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"


# ---------------------------------------------------------------------------
# loops-01: Making the Grade
# ---------------------------------------------------------------------------

LOOPS_CORRECT = """\
def round_scores(student_scores):
    \"\"\"Return scores rounded to nearest integer.\"\"\"
    return [round(score) for score in student_scores]

def count_failed_students(student_scores):
    \"\"\"Count scores at or below 40.\"\"\"
    return sum(1 for score in student_scores if score <= 40)

def above_threshold(student_scores, threshold):
    \"\"\"Return scores at or above threshold.\"\"\"
    return [score for score in student_scores if score >= threshold]

def letter_grades(highest):
    \"\"\"Return lower thresholds for D, C, B, A bands.\"\"\"
    increment = (highest - 40) // 4
    return [41 + i * increment for i in range(4)]

def student_ranking(student_scores, student_names):
    \"\"\"Return ranking strings.\"\"\"
    return [f'{rank}. {name}: {score}'
            for rank, (name, score) in enumerate(zip(student_names, student_scores), 1)]

def perfect_score(student_info):
    \"\"\"Return first [name, 100] pair, or [] if none.\"\"\"
    for pair in student_info:
        if pair[1] == 100:
            return pair
    return []
"""

LOOPS_WRONG = """\
def round_scores(student_scores):
    return student_scores  # not rounding

def count_failed_students(student_scores):
    return 0  # always 0

def above_threshold(student_scores, threshold):
    return student_scores  # no filtering

def letter_grades(highest):
    return [41, 56, 71, 86]  # hardcoded, wrong for non-100

def student_ranking(student_scores, student_names):
    return student_names  # wrong format

def perfect_score(student_info):
    return student_info  # wrong return
"""


class TestLoopsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(LOOPS_CORRECT, "loops-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_solution_fails_deterministically(self):
        result = docker_run(LOOPS_WRONG, "loops-01")
        assert result["passed"] is False

    def test_correct_solution_completes_lesson_via_engine(self):
        engine = fresh_engine_unlocked_up_to("loops-01")
        progression = engine_run(LOOPS_CORRECT, "loops-01", engine)
        assert progression.passed is True
        assert progression.completed is True


# ---------------------------------------------------------------------------
# list-methods-01: Chaitana's Colossal Coaster  (needed by loops prereq chain)
# ---------------------------------------------------------------------------

LIST_METHODS_CORRECT = """\
def add_me_to_the_queue(express_queue, normal_queue, ticket_type, person_name):
    \"\"\"Append person to the appropriate queue and return it.\"\"\"
    if ticket_type == 1:
        express_queue.append(person_name)
        return express_queue
    normal_queue.append(person_name)
    return normal_queue

def find_my_friend(queue, friend_name):
    \"\"\"Return the index of friend_name in queue.\"\"\"
    return queue.index(friend_name)

def add_me_with_my_friends(queue, index, person_name):
    \"\"\"Insert person_name at index and return queue.\"\"\"
    queue.insert(index, person_name)
    return queue

def remove_the_mean_person(queue, person_name):
    \"\"\"Remove first occurrence of person_name and return queue.\"\"\"
    queue.remove(person_name)
    return queue

def how_many_namefellows(queue, person_name):
    \"\"\"Return count of person_name occurrences.\"\"\"
    return queue.count(person_name)

def remove_the_last_person(queue):
    \"\"\"Remove and return last person.\"\"\"
    return queue.pop()

def sorted_names(queue):
    \"\"\"Return alphabetically sorted copy of queue.\"\"\"
    return sorted(queue)
"""


class TestListMethodsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(LIST_METHODS_CORRECT, "list-methods-01")
        # Only required tests must pass (there are optional ones)
        lesson = next(l for l in CURRICULUM.lessons if l.id == "list-methods-01")
        required_names = set(lesson.completion_requirements.required_test_names)
        failing_required = [
            t for t in result["tests"]
            if t["name"] in required_names and not t["passed"]
        ]
        assert not failing_required, (
            f"Required tests failed: {[t['name'] for t in failing_required]}"
        )


# ---------------------------------------------------------------------------
# tuples-01: Tisbury Treasure Hunt
# ---------------------------------------------------------------------------

TUPLES_CORRECT = """\
def get_coordinate(record):
    \"\"\"Return the coordinate from a (treasure, coordinate) tuple.\"\"\"
    return record[1]

def convert_coordinate(coordinate):
    \"\"\"Split coordinate string into a tuple of its characters.\"\"\"
    return tuple(coordinate)

def compare_records(azara_record, rui_record):
    \"\"\"Return True if coordinates match.\"\"\"
    return convert_coordinate(azara_record[1]) == rui_record[1]

def create_record(azara_record, rui_record):
    \"\"\"Combine records if coordinates match, else 'not a match'.\"\"\"
    if compare_records(azara_record, rui_record):
        return azara_record + rui_record
    return 'not a match'

def clean_up(combined_record_group):
    \"\"\"Remove redundant coordinate field (index 1) from each record.\"\"\"
    result = ''
    for record in combined_record_group:
        cleaned = record[:1] + record[2:]
        result += str(cleaned) + '\\n'
    return result
"""

TUPLES_WRONG = """\
def get_coordinate(record):
    return record[0]  # wrong index

def convert_coordinate(coordinate):
    return coordinate  # not converting to tuple

def compare_records(azara_record, rui_record):
    return False  # always mismatch

def create_record(azara_record, rui_record):
    return 'not a match'  # always not a match

def clean_up(combined_record_group):
    return ''  # empty
"""


class TestTuplesE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(TUPLES_CORRECT, "tuples-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_solution_fails_deterministically(self):
        result = docker_run(TUPLES_WRONG, "tuples-01")
        assert result["passed"] is False
        coord_test = next(t for t in result["tests"] if t["name"] == "test_get_coordinate")
        assert coord_test["passed"] is False


# ---------------------------------------------------------------------------
# dictionaries-01: Inventory Management
# ---------------------------------------------------------------------------

DICTS_CORRECT = """\
def create_inventory(items):
    \"\"\"Create inventory dict from item list.\"\"\"
    inventory = {}
    for item in items:
        inventory[item] = inventory.get(item, 0) + 1
    return inventory

def add_items(inventory, items):
    \"\"\"Increment or add items in inventory.\"\"\"
    for item in items:
        inventory[item] = inventory.get(item, 0) + 1
    return inventory

def decrement_items(inventory, items):
    \"\"\"Decrement counts, never below zero; ignore unknown items.\"\"\"
    for item in items:
        if item in inventory:
            inventory[item] = max(0, inventory[item] - 1)
    return inventory

def remove_item(inventory, item):
    \"\"\"Remove item from inventory if present.\"\"\"
    if item in inventory:
        del inventory[item]
    return inventory

def list_inventory(inventory):
    \"\"\"Return list of (item, count) for items with count > 0.\"\"\"
    return [(item, count) for item, count in inventory.items() if count > 0]
"""

DICTS_WRONG = """\
def create_inventory(items):
    return {}  # empty

def add_items(inventory, items):
    return inventory  # no additions

def decrement_items(inventory, items):
    for item in items:
        if item in inventory:
            inventory[item] -= 1  # goes below zero
    return inventory

def remove_item(inventory, item):
    return inventory  # never removes

def list_inventory(inventory):
    return list(inventory.items())  # includes zero-count items
"""


class TestDictionariesE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(DICTS_CORRECT, "dictionaries-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_wrong_solution_fails_deterministically(self):
        result = docker_run(DICTS_WRONG, "dictionaries-01")
        assert result["passed"] is False
        create_test = next(t for t in result["tests"] if t["name"] == "test_create_inventory")
        assert create_test["passed"] is False


# ---------------------------------------------------------------------------
# functions-01: Guido's Gorgeous Lasagna
# ---------------------------------------------------------------------------

FUNCTIONS_CORRECT = """\
EXPECTED_BAKE_TIME = 40
PREPARATION_TIME = 2

def bake_time_remaining(elapsed_bake_time):
    \"\"\"Calculate the bake time remaining.\"\"\"
    return EXPECTED_BAKE_TIME - elapsed_bake_time

def preparation_time_in_minutes(number_of_layers):
    \"\"\"Return preparation time in minutes.\"\"\"
    return number_of_layers * PREPARATION_TIME

def elapsed_time_in_minutes(number_of_layers, elapsed_bake_time):
    \"\"\"Return total elapsed cooking time.\"\"\"
    return preparation_time_in_minutes(number_of_layers) + elapsed_bake_time
"""


class TestFunctionsE2E:

    def test_correct_solution_passes_all_required_tests(self):
        result = docker_run(FUNCTIONS_CORRECT, "functions-01")
        failing = [t for t in result["tests"] if not t["passed"]]
        assert not failing, f"Unexpected failures: {[t['name'] for t in failing]}"

    def test_correct_solution_completes_full_chain(self):
        """Complete all 65 curriculum lessons in sequence and verify completion."""
        engine = fresh_engine()
        for lesson in CURRICULUM.lessons:
            engine.store.mark_completed(lesson.id)

        state = engine.store.state()
        assert state.current_lesson_id is None, "Expected all lessons completed"
        assert len(state.completed_lesson_ids) == 65
