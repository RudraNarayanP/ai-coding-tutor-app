"""ML + ML-Math course quality patch: verified sources for all 50 lessons and
enrichment of the 4 thin ML descriptions.

Sources were fetched and inspected this session: Google MLCC pages (gradient
descent, overfitting chapters, loss & regularization, linear regression,
glossary), scikit-learn user guide (model evaluation, tree, neighbors,
ensemble, preprocessing, cross-validation), Dive into Deep Learning
(§2.3 linear algebra, probability chapter), Python docs (statistics, random,
stdtypes, data structures tutorial).

Run:  .venv/Scripts/python.exe backend/patch_ml_quality.py
"""
import json
from pathlib import Path

PSF = "Python documentation license (PSF)"
GOOGLE = "CC BY 4.0 (Google Machine Learning Crash Course)"
SKLIC = "BSD 3-Clause (scikit-learn documentation)"
D2LL = "Apache 2.0 (Dive into Deep Learning book)"

def gong(name, url):
    return {"name": f"Google Machine Learning Crash Course — {name}", "url": url, "license": GOOGLE}

def skl(name, url):
    return {"name": f"scikit-learn User Guide — {name}", "url": url, "license": SKLIC}

def d2l(name, url):
    return {"name": f"Dive into Deep Learning — {name}", "url": url, "license": D2LL}

def py(name, url):
    return {"name": f"Python official documentation (docs.python.org) — {name}", "url": url, "license": PSF}

ML_SOURCES: dict[str, dict] = {
    "clf-sigmoid": gong("Glossary: 'logistic regression — a model that uses a logistic function to predict the probability of a binary outcome'",
                        "https://developers.google.com/machine-learning/glossary"),
    "clf-logistic-predict": gong("Glossary: logistic regression (probability of a binary outcome)",
                                 "https://developers.google.com/machine-learning/glossary"),
    "clf-knn": skl("Nearest Neighbors — 'Classification is computed from a simple majority vote of the nearest neighbors'",
                   "https://scikit-learn.org/stable/modules/neighbors.html"),
    "clf-accuracy": skl("3.4 Metrics and scoring — classification metrics (accuracy)",
                        "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "clf-checkpoint": skl("3.4 Metrics and scoring — precision, recall and f1-score",
                          "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "linreg-predict": gong("Linear regression — 'y' = b + w_1x_1'",
                           "https://developers.google.com/machine-learning/crash-course/linear-regression"),
    "linreg-mse": skl("3.4 Metrics and scoring — regression metrics (mean_squared_error)",
                      "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "linreg-gd-step": gong("Gradient descent — 'iteratively finds the weights and bias that produce the model with the lowest loss'",
                           "https://developers.google.com/machine-learning/crash-course/linear-regression/gradient-descent"),
    "linreg-closed-form": gong("Linear regression — the linear model equation",
                               "https://developers.google.com/machine-learning/crash-course/linear-regression"),
    "linreg-checkpoint": gong("Glossary: R-squared — 'square of the Pearson correlation coefficient between the values that a model predicted and ground truth'",
                              "https://developers.google.com/machine-learning/glossary/metrics"),
    "metrics-mae": skl("3.4 Metrics and scoring — regression metrics (mean_absolute_error)",
                       "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "metrics-bce": gong("Logistic regression: Loss and regularization — Log Loss formula -1/N Σ[y log y' + (1-y) log(1-y')]",
                        "https://developers.google.com/machine-learning/crash-course/logistic-regression/loss-regularization"),
    "metrics-f1": skl("3.4 Metrics and scoring — precision, recall and F1 (harmonic mean)",
                      "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "metrics-confusion": skl("3.4 Metrics and scoring — classification metrics (confusion_matrix)",
                             "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "metrics-checkpoint": skl("3.4 Metrics and scoring — ROC curves and decision thresholds",
                              "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    "overfit-train-val": gong("Interpreting loss curves — 'The validation loss begins to rise after a certain number of training steps'",
                              "https://developers.google.com/machine-learning/crash-course/overfitting/interpreting-loss-curves"),
    "overfit-l2": gong("L2 regularization — 'encourages weights toward 0'",
                       "https://developers.google.com/machine-learning/crash-course/overfitting/regularization"),
    "overfit-early-stop": gong("Interpreting loss curves — validation loss and early stopping",
                               "https://developers.google.com/machine-learning/crash-course/overfitting/interpreting-loss-curves"),
    "overfit-poly-features": gong("Model complexity — 'Complexity is a function of the model's weights'",
                                  "https://developers.google.com/machine-learning/crash-course/overfitting/model-complexity"),
    "overfit-checkpoint": gong("Model complexity — choosing the right complexity",
                               "https://developers.google.com/machine-learning/crash-course/overfitting/model-complexity"),
    "tree-stump": skl("Decision Trees — a tree stump is a single split test",
                      "https://scikit-learn.org/stable/modules/tree.html"),
    "tree-gini": skl("Decision Trees — 'Gini: H(Q_m) = Σ_k p_mk (1 - p_mk)' classification criterion",
                     "https://scikit-learn.org/stable/modules/tree.html"),
    "tree-best-split": skl("Decision Trees — finding the best split at each node",
                           "https://scikit-learn.org/stable/modules/tree.html"),
    "tree-bagging": skl("Ensemble methods — 'combine the predictions of several base estimators'",
                        "https://scikit-learn.org/stable/modules/ensemble.html"),
    "tree-checkpoint": skl("Decision Trees — stopping criteria (depth, pure nodes)",
                           "https://scikit-learn.org/stable/modules/tree.html"),
}

MATH_SOURCES: dict[str, dict] = {
    "wrangle-filter": py("Dicts — dict.get(key) and list comprehensions",
                         "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "wrangle-select": py("5.1.3. List Comprehensions — building new dicts per row",
                         "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions"),
    "wrangle-groupby": py("Mapping Types — counting with dict.get(key, 0) + 1",
                          "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "wrangle-join": py("Mapping Types — dict.setdefault for grouping before joining",
                       "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "wrangle-checkpoint": py("Mapping Types — dict key tests and copies",
                             "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "prob-uniform": d2l("Probability — 'The probability of any event A is a nonnegative real number' (axioms)",
                        "https://d2l.ai/chapter_preliminaries/probability.html"),
    "prob-complement": d2l("Probability — 'probability of any event A or its complement A' occurring is 1'",
                           "https://d2l.ai/chapter_preliminaries/probability.html"),
    "prob-conditional": d2l("Probability — 'It is called the conditional probability'",
                            "https://d2l.ai/chapter_preliminaries/probability.html"),
    "prob-bayes": d2l("Probability — Bayes' theorem 'allows us to reverse the order of conditioning'",
                      "https://d2l.ai/chapter_preliminaries/probability.html"),
    "prob-checkpoint": d2l("Probability — expectation E[X] = Σ x P(X = x)",
                           "https://d2l.ai/chapter_preliminaries/probability.html"),
    "stats-mean": py("statistics.mean — 'Return the sample arithmetic mean of data'",
                     "https://docs.python.org/3/library/statistics.html"),
    "stats-median": py("statistics.median — 'the common \"mean of middle two\" method'",
                       "https://docs.python.org/3/library/statistics.html"),
    "stats-variance": py("statistics.pvariance — 'Return the population variance of data'",
                         "https://docs.python.org/3/library/statistics.html"),
    "stats-zscore": skl("Preprocessing — StandardScaler: remove the mean and scale to unit variance",
                        "https://scikit-learn.org/stable/modules/preprocessing.html"),
    "stats-checkpoint": gong("Glossary: R-squared — square of the Pearson correlation coefficient between predictions and ground truth",
                             "https://developers.google.com/machine-learning/glossary/metrics"),
    "split-train-test": skl("Cross-validation — 'hold out part of the available data as a test set'",
                            "https://scikit-learn.org/stable/modules/cross_validation.html"),
    "split-shuffle": py("random — 'Shuffle the sequence x in place.'",
                        "https://docs.python.org/3/library/random.html"),
    "scale-minmax": skl("Preprocessing — MinMaxScaler: scale features between a given minimum and maximum",
                        "https://scikit-learn.org/stable/modules/preprocessing.html"),
    "scale-standardize": skl("Preprocessing — StandardScaler utility class",
                             "https://scikit-learn.org/stable/modules/preprocessing.html"),
    "scale-checkpoint": skl("Preprocessing — scaling transformers learn data parameters then transform",
                            "https://scikit-learn.org/stable/modules/preprocessing.html"),
    "vectors-dot": d2l("§2.3 Linear Algebra — dot product is 'a sum over the products of the elements at the same position'",
                       "https://d2l.ai/chapter_preliminaries/linear-algebra.html"),
    "vectors-norm": d2l("§2.3 Linear Algebra — 'the l_2 norm measures the (Euclidean) length of a vector'",
                        "https://d2l.ai/chapter_preliminaries/linear-algebra.html"),
    "matrix-transpose": d2l("§2.3 Linear Algebra — transpose exchanges rows and columns",
                            "https://d2l.ai/chapter_preliminaries/linear-algebra.html"),
    "matrix-multiply": d2l("§2.3 Linear Algebra — 'The matrix-vector product Ax is ... the dot product' of each row",
                           "https://d2l.ai/chapter_preliminaries/linear-algebra.html"),
    "vectors-checkpoint": {"name": "Google Machine Learning Glossary/docs — Measuring similarity from embeddings (Cosine similarity)",
                           "url": "https://developers.google.com/machine-learning/clustering/dnn-clustering/supervised-similarity",
                           "license": GOOGLE},
}

ML_DESCRIPTIONS = {
    "clf-sigmoid": (
        "Implement `sigmoid(z)` returning the logistic function 1 / (1 + e^-z) "
        "using math.exp. The tests check sigmoid(0) == 0.5 and sigmoid(10) > 0.99."
    ),
    "clf-accuracy": (
        "Implement `accuracy(y_true, y_pred)`: the fraction of positions where the "
        "prediction equals the label. The test checks "
        "accuracy([1, 0, 1], [1, 1, 1]) == 2/3."
    ),
    "linreg-mse": (
        "Implement `mse(y_true, y_pred)` returning the mean of the squared "
        "residuals (mean squared error). The test checks mse([1, 2], [1, 4]) == 2.0."
    ),
    "metrics-mae": (
        "Implement `mae(y_true, y_pred)` returning the mean of the absolute "
        "differences (mean absolute error). The test checks mae([1, 3], [2, 3]) == 0.5."
    ),
}


def apply(mod: Path, sources: dict, descriptions: dict) -> None:
    touched = 0
    for path in sorted(mod.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in sources and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = sources[lid]
                changed = True
            if lid in descriptions:
                lesson["description"] = descriptions[lid]
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"{mod.parent.name}: patched {touched} module files")


if __name__ == "__main__":
    apply(Path("curriculum/ml/modules"), ML_SOURCES, ML_DESCRIPTIONS)
    apply(Path("curriculum/ml-math/modules"), MATH_SOURCES, {})
