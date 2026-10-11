"""Intent classifier for the coach / purchase advisor (TF-IDF + logistic regression).

Trained on generated utterances; evaluated on hand-written paraphrases that never appear in training."""

from __future__ import annotations

import random

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.pipeline import FeatureUnion, Pipeline

CATS = ["dining", "food delivery", "groceries", "shopping", "transport", "fuel", "rent", "subscriptions", "entertainment",
        "travel", "electronics", "fashion", "cabs", "eating out", "petrol"]
PERIODS = ["this month", "last month", "this year", "last 3 months", "in august", "in september", "last week", "since january",
           "this week", "yesterday", "", ""]
MERCHANTS = ["swiggy", "zomato", "amazon", "uber", "bigbasket", "netflix", "decathlon", "flipkart", "ola", "myntra"]
ITEMS = ["laptop", "headphones", "running shoes", "phone", "air fryer", "smartwatch", "tv", "bike", "earbuds", "watch"]
AMOUNTS = ["45000", "₹20,000", "rs 5000", "15k", "1.2 lakh", "8,999", "50k", "2000"]
GOALS = ["laptop", "goa trip", "emergency fund", "trip", "vacation"]
MONTHS_W = ["august", "march", "december", "may"]

TRAIN: dict[str, list[str]] = {
    "spend_by_category": ["how much did i spend on {cat} {period}", "what did i spend on {cat}", "total {cat} spending {period}",
                          "show my {cat} expenses {period}", "{cat} spend {period}", "how much went to {cat} {period}",
                          "how much have i spent {period}", "what are my biggest expenses {period}", "where is my money going {period}",
                          "top spending categories {period}", "breakdown of my spending {period}", "spending on {cat}"],
    "compare_periods": ["compare my {cat} spending this month and last month", "did i spend more on {cat} {period} than before",
                        "is my {cat} spending going up", "{cat} this month vs last month", "how does my spending {period} compare to usual",
                        "am i spending more than last month", "compare this month with last month", "spending trend for {cat}",
                        "has my {cat} spend increased"],
    "forecast_query": ["what will my balance be at the end of the month", "will i run out of money", "how much money will i have next month",
                       "forecast my balance", "will my balance go below {amount}", "what is my cash flow for the next 30 days",
                       "predict my balance next month", "am i going to be short on money", "balance projection",
                       "when is my balance lowest", "how low will my balance get"],
    "savings_advice": ["how can i save more", "where can i cut back", "how do i save money", "tips to reduce my spending",
                       "what should i cut to save {amount}", "help me save more each month", "how can i increase my savings rate",
                       "what am i wasting money on", "ways to spend less", "how to save {amount} a month"],
    "subscription_query": ["what subscriptions do i have", "which subscriptions should i cancel", "how much do i pay for subscriptions",
                           "am i paying for anything i don't use", "list my recurring payments", "did any subscription get more expensive",
                           "is {merchant} worth it", "show my subscriptions", "which memberships am i not using"],
    "tax_query": ["which tax regime is better for me", "old or new regime", "how much tax will i pay this year", "how much 80c have i used",
                  "can i save tax", "tax estimate", "how much more can i invest for 80c", "what deductions do i have", "income tax for this year"],
    "goal_query": ["am i on track for my {goal} goal", "how are my goals doing", "when will i reach my {goal} goal",
                   "how much should i save for {goal}", "goal progress", "show my savings goals", "how far am i from my {goal}"],
    "transaction_search": ["show my {merchant} transactions", "when did i last pay {merchant}", "find payments to {merchant}",
                           "how many times did i order from {merchant} {period}", "list {merchant} orders", "show transactions above {amount}",
                           "my last 5 transactions", "what did i buy from {merchant}", "find my rent payments"],
    "affordability_check": ["can i afford a {item} for {amount}", "can i buy a {amount} {item}", "is it ok to spend {amount} on a {item}",
                            "should i buy a {item}", "can i afford {amount}", "is {amount} too much for a {item}", "can i afford the {item}",
                            "do i have enough money for a {item}", "can i spend {amount} today"],
    "recommendation_query": ["suggest {item} under {amount}", "what {item} can i afford", "recommend a {item}", "any good deals for me",
                             "show me picks", "what should i buy", "best {item} within my budget", "find me a cheap {item}",
                             "which {item} fits my budget"],
    "privacy_query": ["what data can you see", "do you read my messages", "which sources are connected", "what do you store about me",
                      "how is my data used", "can you read my emails", "how do i delete my data", "who can see my data",
                      "do you read my otp"],
    "summary_query": ["how am i doing this month", "give me a summary", "how are my finances", "what is my savings rate",
                      "how much did i earn {period}", "monthly summary", "overview of my money", "what is my income {period}",
                      "how much did i save last month"],
    "out_of_scope": ["what's the weather today", "will it rain in chennai tomorrow", "tell me a joke", "who won the cricket match",
                     "what is the capital of france", "write a poem", "how do i cook biryani", "what's the latest news",
                     "translate hello to tamil", "who are you", "hi there", "hello", "thanks", "what time is it",
                     "recommend a movie to watch", "help me with my python code", "what is machine learning",
                     "how tall is mount everest", "play some music", "book a cab for me", "what is the stock price of tcs",
                     "should i invest in bitcoin", "which mutual fund is best", "is the weather nice in {month}"],
}

HELDOUT: dict[str, list[str]] = {
    "spend_by_category": ["total spent on groceries during last month", "money spent eating out in august"],
    "compare_periods": ["was my uber spending higher this month compared to last month", "grocery spend now versus last month"],
    "forecast_query": ["what does my bank balance look like at month end", "is my balance going to dip"],
    "savings_advice": ["suggest ways to put aside more money", "what spending can i reduce"],
    "subscription_query": ["which recurring services am i paying for", "should i drop netflix"],
    "tax_query": ["new tax regime or old one for me", "how much income tax do i owe"],
    "goal_query": ["progress towards the laptop goal", "will i hit my trip goal in time"],
    "transaction_search": ["list every zomato payment", "last time i paid rent"],
    "affordability_check": ["is buying a 60k laptop okay for me", "can i spend 12000 on headphones right now"],
    "recommendation_query": ["recommend headphones within budget", "show running shoes i can afford"],
    "privacy_query": ["are you reading my sms", "what information do you keep"],
    "summary_query": ["summarise my finances", "how much did i make this year"],
    "out_of_scope": ["what's the weather in paris", "tell me something funny"],
}


def generate(seed: int = 5, per_template: int = 4) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    X, y = [], []
    for intent, templates in TRAIN.items():
        for t in templates:
            for _ in range(per_template):
                text = t.format(cat=rng.choice(CATS), period=rng.choice(PERIODS), merchant=rng.choice(MERCHANTS),
                                item=rng.choice(ITEMS), amount=rng.choice(AMOUNTS), goal=rng.choice(GOALS),
                                month=rng.choice(MONTHS_W))
                X.append(" ".join(text.split()))
                y.append(intent)
    return X, y


def make_pipeline() -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("features", feats), ("clf", LogisticRegression(C=10.0, max_iter=3000))])


def train() -> tuple[Pipeline, dict]:
    X, y = generate()
    model = make_pipeline().fit(X, y)
    Xh = [t for ts in HELDOUT.values() for t in ts]
    yh = [k for k, ts in HELDOUT.items() for _ in ts]
    acc = accuracy_score(yh, model.predict(Xh))
    return model, {"train_examples": len(X), "intents": len(TRAIN), "heldout_paraphrases": len(Xh), "heldout_accuracy": round(float(acc), 4)}


def predict(model: Pipeline, text: str) -> tuple[str, float]:
    proba = model.predict_proba([text.lower()])[0]
    i = int(np.argmax(proba))
    return str(model.classes_[i]), float(proba[i])
