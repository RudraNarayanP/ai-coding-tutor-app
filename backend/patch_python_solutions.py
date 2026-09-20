"""Author verified solution_code + source attribution for the 55 Python
foundation lessons that ship tests but never had a canonical answer.

Run from repo root:  .venv/Scripts/python.exe backend/patch_python_solutions.py
Solutions here are validated by backend/verify_lessons.py afterwards.
"""
import json
import sys
from pathlib import Path

MOD_DIR = Path("curriculum/python/modules")

DOC = "Python official documentation (docs.python.org)"
DOC_LIC = "Python documentation license (PSF)"

SOLUTIONS: dict[str, tuple[str, dict]] = {
    # ---------------- numbers ----------------
    "numbers-step-1": (
        "numbers.json",
        "def float_div(a, b):\n    return a / b\n\n\ndef integer_div(a, b):\n    return a // b\n",
        "3.1.1. Numbers — Introduction (division operators)",
        "https://docs.python.org/3/tutorial/introduction.html#numbers",
    ),
    "numbers-step-2": (
        "numbers.json",
        "def get_remainder(dividend, divisor):\n    return dividend % divisor\n",
        "3.1.1. Numbers — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#numbers",
    ),
    "numbers-01": (
        "numbers.json",
        "def exchange_money(budget, exchange_rate):\n"
        "    \"\"\"Return budget divided by exchange_rate.\"\"\"\n"
        "    return budget / exchange_rate\n\n\n"
        "def get_change(budget, exchanging_value):\n"
        "    \"\"\"Return what is left after exchanging.\"\"\"\n"
        "    return budget - exchanging_value\n\n\n"
        "def get_value_of_bills(denomination, number_of_bills):\n"
        "    \"\"\"Return total value of bills.\"\"\"\n"
        "    return denomination * number_of_bills\n\n\n"
        "def get_number_of_bills(amount, denomination):\n"
        "    \"\"\"Return how many whole bills fit in amount.\"\"\"\n"
        "    return amount // denomination\n\n\n"
        "def get_leftover_of_bills(amount, denomination):\n"
        "    \"\"\"Return leftover after exchanging into whole bills.\"\"\"\n"
        "    return amount % denomination\n\n\n"
        "def exchangeable_value(budget, exchange_rate, spread, denomination):\n"
        "    \"\"\"Return max value obtainable in whole bills after spread fee.\"\"\"\n"
        "    actual_rate = exchange_rate * (1 + spread / 100)\n"
        "    exchanged = budget / actual_rate\n"
        "    return exchanged - exchanged % denomination\n",
        "3.1.1. Numbers — Introduction (arithmetic operators, //, %)",
        "https://docs.python.org/3/tutorial/introduction.html#numbers",
    ),
    "numbers-practice-1": (
        "numbers.json",
        "def split_bill(total_bill, tip_percentage, people):\n"
        "    return total_bill * (1 + tip_percentage / 100) / people\n",
        "3.1.1. Numbers — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#numbers",
    ),
    "numbers-checkpoint": (
        "numbers.json",
        "def convert_hours_to_minutes(hours):\n    return hours * 60\n",
        "3.1.1. Numbers — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#numbers",
    ),
    # ---------------- conditionals ----------------
    "conditionals-step-1": (
        "conditionals.json",
        'def evaluate_grade(score):\n    if score >= 50:\n        return "Pass"\n    return "Fail"\n',
        "4.1. if Statements — Conditional Control",
        "https://docs.python.org/3/tutorial/controlflow.html#if-statements",
    ),
    "conditionals-step-2": (
        "conditionals.json",
        'def temperature_status(temp):\n    if temp < 15:\n        return "Cold"\n'
        '    elif temp <= 28:\n        return "Warm"\n    return "Hot"\n',
        "4.1. if Statements — Conditional Control",
        "https://docs.python.org/3/tutorial/controlflow.html#if-statements",
    ),
    "conditionals-01": (
        "conditionals.json",
        "def is_criticality_balanced(temperature, neutrons_emitted):\n"
        '    """Return True when reactor is balanced."""\n'
        "    return temperature < 800 and neutrons_emitted > 500\n\n\n"
        "def reactor_efficiency(voltage, current, theoretical_max_power):\n"
        '    """Return efficiency band as a colour string."""\n'
        "    percentage_value = ((voltage * current) / theoretical_max_power) * 100\n"
        '    if percentage_value >= 80:\n        return "green"\n'
        '    if percentage_value >= 60:\n        return "orange"\n'
        '    if percentage_value >= 30:\n        return "red"\n'
        '    return "black"\n\n\n'
        "def fail_safe(temperature, neutrons_produced_per_second, threshold):\n"
        '    """Return safety status string."""\n'
        "    if temperature * neutrons_produced_per_second < 0.9 * threshold:\n"
        '        return "LOW"\n'
        "    if temperature * neutrons_produced_per_second <= 1.1 * threshold:\n"
        '        return "NORMAL"\n'
        '    return "DANGER"\n',
        "Boolean Operations — Language Reference (and / or / not)",
        "https://docs.python.org/3/reference/expressions.html#boolean-operations",
    ),
    "conditionals-practice-1": (
        "conditionals.json",
        'def traffic_action(color):\n    if color == "red":\n        return "Stop"\n'
        '    if color == "yellow":\n        return "Prepare"\n    return "Go"\n',
        "4.1. if Statements — Conditional Control",
        "https://docs.python.org/3/tutorial/controlflow.html#if-statements",
    ),
    "conditionals-checkpoint": (
        "conditionals.json",
        "def discount_rate(is_member, total_spent):\n"
        "    if is_member and total_spent >= 100:\n        return 0.2\n"
        "    if is_member:\n        return 0.1\n    return 0.0\n",
        "4.1. if Statements — Conditional Control",
        "https://docs.python.org/3/tutorial/controlflow.html#if-statements",
    ),
    # ---------------- comparisons ----------------
    "comparisons-step-1": (
        "comparisons.json",
        "def is_equal(a, b):\n    return a == b\n\n\ndef is_greater(a, b):\n    return a > b\n",
        "Comparisons — Expressions (Language Reference) — Expressions",
        "https://docs.python.org/3/reference/expressions.html#comparisons",
    ),
    "comparisons-step-2": (
        "comparisons.json",
        "def in_range(x, low, high):\n    return low <= x <= high\n",
        "Comparisons — chained comparisons (Language Reference)",
        "https://docs.python.org/3/reference/expressions.html#comparisons",
    ),
    "comparisons-01": (
        "comparisons.json",
        "FACE_CARDS = {'K', 'Q', 'J'}\n\n\n"
        "def value_of_card(card):\n"
        '    """Return numeric value of a card."""\n'
        "    if card in FACE_CARDS:\n        return 10\n"
        '    if card == "A":\n        return 1\n'
        "    return int(card)\n\n\n"
        "def higher_card(card_one, card_two):\n"
        '    """Return the higher card, or both as a tuple if equal."""\n'
        "    v1, v2 = value_of_card(card_one), value_of_card(card_two)\n"
        "    if v1 > v2:\n        return card_one\n"
        "    if v2 > v1:\n        return card_two\n"
        "    return (card_one, card_two)\n\n\n"
        "def value_of_ace(card_one, card_two):\n"
        '    """Return 11 if safe, else 1."""\n'
        "    total = value_of_card(card_one) + value_of_card(card_two)\n"
        '    if card_one == "A":\n        total += 10\n'
        '    if card_two == "A":\n        total += 10\n'
        "    return 11 if total + 11 <= 21 else 1\n\n\n"
        "def is_blackjack(card_one, card_two):\n"
        '    """Return True if hand totals 21 with an ace and a 10-value card."""\n'
        "    cards = (card_one, card_two)\n"
        "    return 'A' in cards and any(value_of_card(c) == 10 for c in cards)\n\n\n"
        "def can_split_pairs(card_one, card_two):\n"
        '    """Return True if cards have equal value."""\n'
        "    return value_of_card(card_one) == value_of_card(card_two)\n\n\n"
        "def can_double_down(card_one, card_two):\n"
        '    """Return True if hand totals 9, 10, or 11."""\n'
        "    return value_of_card(card_one) + value_of_card(card_two) in (9, 10, 11)\n",
        "Comparisons — Expressions (Language Reference) — Expressions",
        "https://docs.python.org/3/reference/expressions.html#comparisons",
    ),
    "comparisons-practice-1": (
        "comparisons.json",
        "def can_ride(age, height_cm):\n    return age >= 10 and height_cm >= 130\n",
        "Comparisons — Expressions (Language Reference) — Expressions",
        "https://docs.python.org/3/reference/expressions.html#comparisons",
    ),
    "comparisons-checkpoint": (
        "comparisons.json",
        'def compare_scores(score_a, score_b):\n    if score_a > score_b:\n        return "A"\n'
        '    if score_b > score_a:\n        return "B"\n    return "Tie"\n',
        "Comparisons — Expressions (Language Reference) — Expressions",
        "https://docs.python.org/3/reference/expressions.html#comparisons",
    ),
    # ---------------- strings ----------------
    "strings-step-1": (
        "strings.json",
        "def combine(a, b):\n    return a + b\n\n\ndef get_first_and_last(s):\n    return s[0] + s[-1]\n",
        "3.1.2. Text (Strings) — indexing and concatenation",
        "https://docs.python.org/3/tutorial/introduction.html#strings",
    ),
    "strings-step-2": (
        "strings.json",
        "def drop_last_char(s):\n    return s[:-1]\n\n\ndef get_prefix(s, n):\n    return s[:n]\n",
        "3.1.2. Text (Strings) — slicing",
        "https://docs.python.org/3/tutorial/introduction.html#strings",
    ),
    "strings-01": (
        "strings.json",
        "def add_prefix_un(word):\n"
        '    """Return word with \'un\' prefix."""\n'
        "    return 'un' + word\n\n\n"
        "def make_word_groups(vocab_words):\n"
        '    """Return prefix and prefixed words joined by \' :: \'."""\n'
        "    prefix = vocab_words[0]\n"
        "    return ' :: '.join([prefix] + [prefix + w for w in vocab_words[1:]])\n\n\n"
        "def remove_suffix_ness(word):\n"
        '    """Remove -ness suffix, fixing iness -> y spelling."""\n'
        "    root = word[:-4]\n"
        "    if root.endswith('i'):\n        return root[:-1] + 'y'\n"
        "    return root\n\n\n"
        "def adjective_to_verb(sentence, index):\n"
        '    """Return the word at index with -en appended, removing trailing punctuation."""\n'
        "    word = sentence.split()[index]\n"
        "    return word.rstrip('.') + 'en'\n",
        "Common Sequence Operations — indexing, slicing and join",
        "https://docs.python.org/3/library/stdtypes.html#sequence-types-list-tuple-range",
    ),
    "strings-practice-1": (
        "strings.json",
        'def format_badge(name, role):\n    return "ID: " + name + " (" + role + ")"\n',
        "3.1.2. Text (Strings) — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#strings",
    ),
    "strings-checkpoint": (
        "strings.json",
        "def wrap_string(s, char):\n    return char + s + char\n",
        "3.1.2. Text (Strings) — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#strings",
    ),
    # ---------------- string_methods ----------------
    "string-methods-step-1": (
        "string_methods.json",
        "def make_loud(s):\n    return s.upper()\n\n\ndef is_question(s):\n    return s.endswith('?')\n",
        "String Methods — Text Sequence Type str",
        "https://docs.python.org/3/library/stdtypes.html#string-methods",
    ),
    "string-methods-step-2": (
        "string_methods.json",
        "def clean_and_censor(s, word, mask):\n    return s.strip().replace(word, mask)\n",
        "String Methods — Text Sequence Type str",
        "https://docs.python.org/3/library/stdtypes.html#string-methods",
    ),
    "string-methods-01": (
        "string_methods.json",
        "def capitalize_title(title):\n"
        '    """Return title in title case."""\n'
        "    return title.title()\n\n\n"
        "def check_sentence_ending(sentence):\n"
        '    """Return True if sentence ends with a period."""\n'
        "    return sentence.endswith('.')\n\n\n"
        "def clean_up_spacing(sentence):\n"
        '    """Strip leading and trailing whitespace."""\n'
        "    return sentence.strip()\n\n\n"
        "def replace_word_choice(sentence, old_word, new_word):\n"
        '    """Replace old_word with new_word in sentence."""\n'
        "    return sentence.replace(old_word, new_word)\n",
        "String Methods — Text Sequence Type str",
        "https://docs.python.org/3/library/stdtypes.html#string-methods",
    ),
    "string-methods-practice-1": (
        "string_methods.json",
        "def sanitize_email(raw_email):\n    return raw_email.strip().lower()\n",
        "String Methods — Text Sequence Type str",
        "https://docs.python.org/3/library/stdtypes.html#string-methods",
    ),
    "string-methods-checkpoint": (
        "string_methods.json",
        'def hashtagify(word):\n    return "#" + word.strip().lower()\n',
        "String Methods — Text Sequence Type str",
        "https://docs.python.org/3/library/stdtypes.html#string-methods",
    ),
    # ---------------- lists ----------------
    "lists-step-1": (
        "lists.json",
        "def get_first_and_sum(numbers):\n    return (numbers[0], sum(numbers))\n",
        "3.1.3. Lists — Introduction (indexing, len, sum)",
        "https://docs.python.org/3/tutorial/introduction.html#lists",
    ),
    "lists-step-2": (
        "lists.json",
        "def combine_and_check(list1, list2, target):\n    combined = list1 + list2\n    return target in combined\n",
        "3.1.3. Lists — Introduction (concatenation, membership)",
        "https://docs.python.org/3/tutorial/introduction.html#lists",
    ),
    "lists-01": (
        "lists.json",
        "def get_rounds(number):\n"
        '    """Return current and next two round numbers."""\n'
        "    return [number, number + 1, number + 2]\n\n\n"
        "def concatenate_rounds(rounds_1, rounds_2):\n"
        '    """Concatenate two round lists."""\n'
        "    return rounds_1 + rounds_2\n\n\n"
        "def list_contains_round(rounds, number):\n"
        '    """Return True if number is in rounds."""\n'
        "    return number in rounds\n\n\n"
        "def card_average(hand):\n"
        '    """Return average card value."""\n'
        "    return sum(hand) / len(hand)\n\n\n"
        "def approx_average_is_average(hand):\n"
        '    """Return True if first/last average or middle card equals true average."""\n'
        "    true_avg = card_average(hand)\n"
        "    flat_avg = (hand[0] + hand[-1]) / 2\n"
        "    median = hand[len(hand) // 2]\n"
        "    return true_avg in (flat_avg, median)\n\n\n"
        "def average_even_is_average_odd(hand):\n"
        '    """Return True if even-indexed average equals odd-indexed average."""\n'
        "    return card_average(hand[::2]) == card_average(hand[1::2])\n\n\n"
        "def maybe_double_last(hand):\n"
        '    """Double the last card if it is a Jack (11)."""\n'
        "    if hand[-1] == 11:\n        hand[-1] = 22\n"
        "    return hand\n",
        "3.1.3. Lists — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#lists",
    ),
    "lists-practice-1": (
        "lists.json",
        "def total_weight(item_weights):\n    return sum(item_weights)\n",
        "3.1.3. Lists — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#lists",
    ),
    "lists-checkpoint": (
        "lists.json",
        "def middle_element(lst):\n    return lst[len(lst) // 2]\n",
        "3.1.3. Lists — Introduction",
        "https://docs.python.org/3/tutorial/introduction.html#lists",
    ),
    # ---------------- list_methods ----------------
    "list-methods-step-1": (
        "list_methods.json",
        "def manage_queue(queue, person):\n    queue.append(person)\n    return queue\n",
        "5.1.1. Lists as Stacks — Data Structures (append/pop)",
        "https://docs.python.org/3/tutorial/datastructures.html",
    ),
    "list-methods-step-2": (
        "list_methods.json",
        "def count_and_sort(lst, target):\n    return (lst.count(target), sorted(lst))\n",
        "5.1. More on Lists (count) + Sorting — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#sorting-lists",
    ),
    "list-methods-01": (
        "list_methods.json",
        "def add_me_to_the_queue(express_queue, normal_queue, ticket_type, person_name):\n"
        '    """Append person to the appropriate queue and return it."""\n'
        "    queue = express_queue if ticket_type == 1 else normal_queue\n"
        "    queue.append(person_name)\n    return queue\n\n\n"
        "def find_my_friend(queue, friend_name):\n"
        '    """Return the index of friend_name in queue."""\n'
        "    return queue.index(friend_name)\n\n\n"
        "def add_me_with_my_friends(queue, index, person_name):\n"
        '    """Insert person_name at index and return queue."""\n'
        "    queue.insert(index, person_name)\n    return queue\n\n\n"
        "def remove_the_mean_person(queue, person_name):\n"
        '    """Remove first occurrence of person_name and return queue."""\n'
        "    queue.remove(person_name)\n    return queue\n\n\n"
        "def how_many_namefellows(queue, person_name):\n"
        '    """Return count of person_name occurrences."""\n'
        "    return queue.count(person_name)\n\n\n"
        "def remove_the_last_person(queue):\n"
        '    """Remove and return last person."""\n'
        "    return queue.pop()\n\n\n"
        "def sorted_names(queue):\n"
        '    """Return alphabetically sorted copy of queue."""\n'
        "    return sorted(queue)\n",
        "Mutable Sequence Types — Methods of Lists (Standard Types)",
        "https://docs.python.org/3/tutorial/datastructures.html#more-on-lists",
    ),
    "list-methods-practice-1": (
        "list_methods.json",
        "def process_task(task_stack):\n"
        "    if task_stack:\n        return task_stack.pop()\n    return None\n",
        "5.1.1. Lists as Stacks — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html",
    ),
    "list-methods-checkpoint": (
        "list_methods.json",
        "def reverse_and_sort(lst):\n    return sorted(lst, reverse=True)\n",
        "Sorting — sorted() (Built-in Functions) — sorted()",
        "https://docs.python.org/3/howto/sorting.html",
    ),
    # ---------------- loops ----------------
    "loops-step-1": (
        "loops.json",
        "def sum_squares(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i * i\n    return total\n",
        "4.2. for Statements — Conditional Control (range())",
        "https://docs.python.org/3/tutorial/controlflow.html#for-statements",
    ),
    "loops-step-2": (
        "loops.json",
        "def double_evens(numbers):\n    return [x * 2 for x in numbers if x % 2 == 0]\n",
        "5.1.3. List Comprehensions — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions",
    ),
    "loops-01": (
        "loops.json",
        "def round_scores(student_scores):\n"
        '    """Return scores rounded to nearest integer."""\n'
        "    return [round(score) for score in student_scores]\n\n\n"
        "def count_failed_students(student_scores):\n"
        '    """Count scores at or below 40."""\n'
        "    return sum(1 for score in student_scores if score <= 40)\n\n\n"
        "def above_threshold(student_scores, threshold):\n"
        '    """Return scores at or above threshold."""\n'
        "    return [score for score in student_scores if score >= threshold]\n\n\n"
        "def letter_grades(highest):\n"
        '    """Return lower thresholds for D, C, B, A bands."""\n'
        "    increment = (highest - 40) // 4\n"
        "    return [41 + i * increment for i in range(4)]\n\n\n"
        "def student_ranking(student_scores, student_names):\n"
        '    """Return ranking strings."""\n'
        "    return [f'{index}. {name}: {score}'\n"
        "            for index, (name, score) in enumerate(zip(student_names, student_scores), start=1)]\n\n\n"
        "def perfect_score(student_info):\n"
        '    """Return first [name, 100] pair, or [] if none."""\n'
        "    for name, score in student_info:\n"
        "        if score == 100:\n            return [name, 100]\n"
        "    return []\n",
        "4.2. for Statements + 5.6. Looping Techniques (enumerate)",
        "https://docs.python.org/3/tutorial/controlflow.html#for-statements",
    ),
    "loops-practice-1": (
        "loops.json",
        "def apply_discounts(prices, discount_pct):\n"
        "    return [p * (1 - discount_pct / 100) for p in prices]\n",
        "5.1.3. List Comprehensions — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions",
    ),
    "loops-checkpoint": (
        "loops.json",
        "def filter_long_words(words, min_len):\n    return [w for w in words if len(w) >= min_len]\n",
        "5.1.3. List Comprehensions — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions",
    ),
    # ---------------- tuples ----------------
    "tuples-step-1": (
        "tuples.json",
        "def make_point(x, y):\n    return (x, y)\n\n\ndef get_x(point):\n    return point[0]\n",
        "Tuple Types — Built-in Types (immutable sequences)",
        "https://docs.python.org/3/library/stdtypes.html#tuple-types",
    ),
    "tuples-step-2": (
        "tuples.json",
        "def swap_and_combine(t1, t2):\n"
        "    a, b = t1\n    c, d = t2\n    return (b, a, d, c)\n",
        "Tuple Types — Built-in Types (unpacking)",
        "https://docs.python.org/3/library/stdtypes.html#tuple-types",
    ),
    "tuples-01": (
        "tuples.json",
        "def get_coordinate(record):\n"
        '    """Return the coordinate from a (treasure, coordinate) tuple."""\n'
        "    return record[1]\n\n\n"
        "def convert_coordinate(coordinate):\n"
        '    """Split coordinate string into a tuple of its characters."""\n'
        "    return tuple(coordinate)\n\n\n"
        "def compare_records(azara_record, rui_record):\n"
        '    """Return True if coordinates match."""\n'
        "    return convert_coordinate(get_coordinate(azara_record)) == rui_record[1]\n\n\n"
        "def create_record(azara_record, rui_record):\n"
        '    """Combine records if coordinates match, else \'not a match\'."""\n'
        "    if compare_records(azara_record, rui_record):\n"
        "        return azara_record + rui_record\n"
        "    return 'not a match'\n\n\n"
        "def clean_up(combined_record_group):\n"
        '    """Remove redundant coordinate field (index 1) from each record."""\n'
        "    report = (str(record[:1] + record[2:]) + '\\n'\n"
        "            for record in combined_record_group)\n"
        "    return ''.join(report)\n",
        "Tuple Types — Built-in Types",
        "https://docs.python.org/3/library/stdtypes.html#tuple-types",
    ),
    "tuples-practice-1": (
        "tuples.json",
        'def format_location(coord):\n    lat, lon = coord\n    return f"Lat: {lat}, Lon: {lon}"\n',
        "Tuple Types — Built-in Types (unpacking)",
        "https://docs.python.org/3/library/stdtypes.html#tuple-types",
    ),
    "tuples-checkpoint": (
        "tuples.json",
        "def get_min_max(numbers):\n    return (min(numbers), max(numbers))\n",
        "min() and max() — Built-in Functions",
        "https://docs.python.org/3/library/functions.html#min",
    ),
    # ---------------- dictionaries ----------------
    "dictionaries-step-1": (
        "dictionaries.json",
        "def get_item_count(inventory, item):\n    return inventory.get(item, 0)\n",
        "Mapping Types — dict.get() (Standard Types)",
        "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict",
    ),
    "dictionaries-step-2": (
        "dictionaries.json",
        "def total_inventory_count(inventory):\n    return sum(inventory.values())\n",
        "5.5. Dictionaries — Data Structures (view objects)",
        "https://docs.python.org/3/tutorial/datastructures.html#dictionaries",
    ),
    "dictionaries-01": (
        "dictionaries.json",
        "def create_inventory(items):\n"
        '    """Create inventory dict from item list."""\n'
        "    inventory = {}\n"
        "    for item in items:\n"
        "        inventory[item] = inventory.get(item, 0) + 1\n"
        "    return inventory\n\n\n"
        "def add_items(inventory, items):\n"
        '    """Increment or add items in inventory."""\n'
        "    for item in items:\n"
        "        inventory[item] = inventory.get(item, 0) + 1\n"
        "    return inventory\n\n\n"
        "def decrement_items(inventory, items):\n"
        '    """Decrement counts, never below zero; ignore unknown items."""\n'
        "    for item in items:\n"
        "        if item in inventory and inventory[item] > 0:\n"
        "            inventory[item] -= 1\n"
        "    return inventory\n\n\n"
        "def remove_item(inventory, item):\n"
        '    """Remove item from inventory if present."""\n'
        "    if item in inventory:\n        del inventory[item]\n"
        "    return inventory\n\n\n"
        "def list_inventory(inventory):\n"
        '    """Return list of (item, count) for items with count > 0."""\n'
        "    return [(item, count) for item, count in inventory.items() if count > 0]\n",
        "5.5. Dictionaries — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#dictionaries",
    ),
    "dictionaries-practice-1": (
        "dictionaries.json",
        "def count_words(words):\n"
        "    counts = {}\n"
        "    for word in words:\n"
        "        counts[word] = counts.get(word, 0) + 1\n"
        "    return counts\n",
        "5.5. Dictionaries — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#dictionaries",
    ),
    "dictionaries-checkpoint": (
        "dictionaries.json",
        "def merge_inventories(inv1, inv2):\n"
        "    merged = dict(inv1)\n"
        "    for item, count in inv2.items():\n"
        "        merged[item] = merged.get(item, 0) + count\n"
        "    return merged\n",
        "5.5. Dictionaries — Data Structures",
        "https://docs.python.org/3/tutorial/datastructures.html#dictionaries",
    ),
    # ---------------- functions ----------------
    "functions-step-1": (
        "functions.json",
        "def double(x):\n    return x * 2\n",
        "4.8. Defining Functions — Control Flow",
        "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
    ),
    "functions-step-2": (
        "functions.json",
        'def area_of_rectangle(width, height):\n    """Calculate rectangle area."""\n    return width * height\n',
        "4.8. Defining Functions (docstrings) — Control Flow",
        "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
    ),
    "functions-01": (
        "functions.json",
        'EXPECTED_BAKE_TIME = 40\n'
        "PREPARATION_TIME = 2\n\n\n"
        "def bake_time_remaining(elapsed_bake_time):\n"
        '    """Calculate the bake time remaining.\n\n'
        "    Parameters:\n        elapsed_bake_time (int): The baking time already elapsed.\n\n"
        "    Returns:\n        int: Remaining bake time derived from EXPECTED_BAKE_TIME.\n"
        '    """\n'
        "    return EXPECTED_BAKE_TIME - elapsed_bake_time\n\n\n"
        "def preparation_time_in_minutes(number_of_layers):\n"
        '    """Calculate total preparation time for the given number of layers."""\n'
        "    return number_of_layers * PREPARATION_TIME\n\n\n"
        "def elapsed_time_in_minutes(number_of_layers, elapsed_bake_time):\n"
        '    """Return total elapsed time (preparation plus baking)."""\n'
        "    return preparation_time_in_minutes(number_of_layers) + elapsed_bake_time\n",
        "4.8. Defining Functions — Control Flow",
        "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
    ),
    "functions-practice-1": (
        "functions.json",
        "def scale_recipe(base_amount, base_servings, target_servings):\n"
        '    """Return scaled amount for target_servings."""\n'
        "    return base_amount * (target_servings / base_servings)\n",
        "4.8. Defining Functions — Control Flow",
        "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
    ),
    "functions-checkpoint": (
        "functions.json",
        'def is_even(n):\n    """Return True if n is even."""\n    return n % 2 == 0\n',
        "4.8. Defining Functions — Control Flow",
        "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
    ),
}


def main() -> int:
    modified: dict[str, dict] = {}
    for lid, (module_file, code, section, url) in SOLUTIONS.items():
        path = MOD_DIR / module_file
        data = modified.get(module_file)
        if data is None:
            data = modified[module_file] = json.loads(path.read_text(encoding="utf-8"))
        lesson = next(l for l in data["lessons"] if l["id"] == lid)
        if lesson.get("solution_code"):
            print(f"skip {lid}: solution already present")
            continue
        lesson["solution_code"] = code
        if not (lesson.get("source") or {}).get("url"):
            lesson["source"] = {
                "name": f"{DOC} — {section}",
                "url": url,
                "license": DOC_LIC,
            }
        print(f"added solution for {lid}")
    for module_file, data in modified.items():
        (MOD_DIR / module_file).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"rewrote {len(modified)} module files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
