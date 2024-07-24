from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import re
from agent_network import get_response

app = Flask(__name__)
CORS(app)

def format_summary_to_html(summary_content):
    lines = summary_content.split('\n')
    formatted_lines = []
    in_list = False
    list_item_content = []

    def process_emphasis(text):
        # Convert **text** to <strong>text</strong>
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        # Convert *text* to <em>text</em>
        text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
        return text

    def process_cli_commands(text):
        # Pattern to match CLI commands (starting with 'aws', 'git', etc., or enclosed in backticks)
        cli_pattern = r'(`[^`]+`|(?<!\S)(?:aws|git|npm|docker|kubectl)\s+[^:\n]+)'
        
        def replace_command(match):
            command = match.group(1)
            # Remove backticks if present
            command = command.strip('`')
            return f'<code>{command}</code>'
        
        return re.sub(cli_pattern, replace_command, text)

    for line in lines:
        # Check if line is a numbered list item
        list_match = re.match(r'^(\d+)\.\s*(.*)', line)
        if list_match:
            if list_item_content:
                formatted_lines.append(''.join(list_item_content))
                list_item_content = []
            if not in_list:
                formatted_lines.append('<ol>')
                in_list = True
            number, content = list_match.groups()
            processed_content = process_cli_commands(process_emphasis(content))
            list_item_content.append(f'<li>{processed_content}')
        elif in_list and not line.strip():
            if list_item_content:
                formatted_lines.append(''.join(list_item_content) + '</li>')
                list_item_content = []
            formatted_lines.append('</ol>')
            in_list = False
        else:
            line = process_cli_commands(process_emphasis(line))
            
            if in_list:
                list_item_content.append(f'<p>{line}</p>')
            else:
                formatted_lines.append(f'<p>{line}</p>')

    if list_item_content:
        formatted_lines.append(''.join(list_item_content) + '</li>')
    if in_list:
        formatted_lines.append('</ol>')

    formatted_html = '\n'.join(formatted_lines)

    final_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>CloudDefense.AI Assistant</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            padding: 20px;
        }}
        code {{
            display: block;
            background-color: #f4f4f4;
            padding: 6px;
            margin: 3px 0;
            border-radius: 4px;
            white-space: pre-wrap;
            word-break: break-all;
            font-size: 14px;
        }}
        p {{
            margin: 0 0 10px;
        }}
        ol {{
            padding-left: 20px;
        }}
        li {{
            margin-bottom: 10px;
        }}
        strong {{
            font-weight: bold;
        }}
        em {{
            font-style: italic;
        }}
    </style>
</head>
<body>
    {formatted_html}
</body>
</html>"""

    return final_html

@app.route('/')
def ping():
    return 'Pong!'

@app.route('/welcome', methods=['GET'])
def welcome():
    welcome_message = "Hi👋, I am CloudDefense.AI assistant. How can I help you today?"
    formatted_html = format_summary_to_html(welcome_message)
    return jsonify({"message": formatted_html})

@app.route('/query', methods=['POST'])
def query():
    body = request.json
    res = get_response(body['query'])
    formatted_html = format_summary_to_html(res)
    return jsonify({"message": formatted_html})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)