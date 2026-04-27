import json
from collections import defaultdict
from profiler import load_dataset, detect_pathologies

def run_eval():
    dataset = load_dataset("nevup_seed_dataset.json")
    ground_truth = {t["userId"]: set(t["pathologies"]) for t in dataset["groundTruthLabels"]}
    
    classes = dataset["meta"]["schema"]["pathologyLabels"]
    
    stats = {c: {"TP": 0, "FP": 0, "FN": 0} for c in classes}
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    
    for trader in dataset.get("traders", []):
        user_id = trader["userId"]
        truth = ground_truth.get(user_id, set())
        
        detected_profiles = detect_pathologies(trader)
        predictions = set(p["pathology"] for p in detected_profiles)
        
        for c in classes:
            if c in truth and c in predictions:
                stats[c]["TP"] += 1
            elif c not in truth and c in predictions:
                stats[c]["FP"] += 1
            elif c in truth and c not in predictions:
                stats[c]["FN"] += 1
                
        for t_label in truth:
            if not predictions:
                confusion_matrix[t_label]["None"] += 1
            for p_label in predictions:
                confusion_matrix[t_label][p_label] += 1
                
    report = {}
    macro_p = macro_r = macro_f1 = 0
    count_classes = len(classes)
    
    for c in classes:
        tp = stats[c]["TP"]
        fp = stats[c]["FP"]
        fn = stats[c]["FN"]
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        report[c] = {
            "precision": round(precision, 2),
            "recall": round(recall, 2),
            "f1": round(f1, 2)
        }
        
        macro_p += precision
        macro_r += recall
        macro_f1 += f1
        
    report["macro_avg"] = {
        "precision": round(macro_p / count_classes, 2),
        "recall": round(macro_r / count_classes, 2),
        "f1": round(macro_f1 / count_classes, 2)
    }
    
    with open("eval_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    html_content = """
    <html>
    <head><title>Eval Report</title>
    <style>
        body { font-family: sans-serif; margin: 40px; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 30px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
    </head>
    <body>
        <h1>Coaching System Evaluation Report</h1>
        <h2>Classification Metrics</h2>
        <table>
            <tr><th>Pathology</th><th>Precision</th><th>Recall</th><th>F1-Score</th></tr>
    """
    for c in classes:
        html_content += f"""
            <tr>
                <td>{c}</td>
                <td>{report[c]['precision']}</td>
                <td>{report[c]['recall']}</td>
                <td>{report[c]['f1']}</td>
            </tr>
        """
    html_content += f"""
            <tr style="font-weight: bold; background-color: #eee;">
                <td>Macro Avg</td>
                <td>{report['macro_avg']['precision']}</td>
                <td>{report['macro_avg']['recall']}</td>
                <td>{report['macro_avg']['f1']}</td>
            </tr>
        </table>
        
        <h2>Confusion Matrix</h2>
        <p>Rows: True Label | Columns: Predicted Label</p>
        <table>
            <tr><th>True \\ Pred</th>
    """
    html_content += "".join(f"<th>{c}</th>" for c in classes) + "<th>None</th></tr>"
    
    for t_label in classes:
        html_content += f"<tr><td><strong>{t_label}</strong></td>"
        for p_label in classes:
            html_content += f"<td>{confusion_matrix[t_label][p_label]}</td>"
        html_content += f"<td>{confusion_matrix[t_label]['None']}</td></tr>"
        
    html_content += """
        </table>
    </body>
    </html>
    """
    with open("eval_report.html", "w") as f:
        f.write(html_content)

if __name__ == "__main__":
    run_eval()
    print("Generated eval_report.json and eval_report.html")
