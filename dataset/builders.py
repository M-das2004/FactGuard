"""Small helper shared by the dataset files."""


def task(task_id, language, family, label, fault, requirement, code, function, hidden,
         hidden_property=None, origin="extra"):
    """One evaluation task.

    hidden           [(args, expected), ...] - ground truth, never shown to any system
    hidden_property  "args_unchanged" when the bug is a side effect that no output
                     comparison can see (the code must also leave its input alone)
    """
    return {
        "id": task_id, "language": language, "family": family, "label": label, "fault": fault,
        "requirement": requirement, "code": code, "function": function,
        "hidden": [{"args": a, "expected": e} for a, e in hidden],
        "hidden_property": hidden_property, "origin": origin,
    }
