import operator
import functools
import json
from typing import Annotated, Literal, Sequence, TypedDict
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder,
)
from langgraph.graph import END, StateGraph, START
from langgraph.errors import GraphRecursionError
from dotenv import load_dotenv

load_dotenv()

# Load the reference rules
with open('rules.json', 'r') as f:
    reference_rules = json.load(f)

# Load the misconfigurations data
with open('misconfigurations.json', 'r') as f:
    misconfigurations_data = json.load(f)

template = """You are a helpful assistant whose goal is to help implement various cloud security policies in customers' AWS cloud configurations.

You have access to a set of reference rules for cloud security. Use these rules to guide your analysis and recommendations.

Answer the following questions as best you can. Assume that you have access to the customers' AWS cloud console and CLI and that you are allowed to run arbitrary commands to achieve your goal.

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {messages}
Thought:"""

react_prompt = PromptTemplate.from_template(template)

llm = ChatGroq(
    model="llama3-70b-8192",
)

def create_agent(llm, tools, system_message: str):
    """Create an agent."""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK, another assistant with different tools "
                " will help where you left off. Execute what you can to make progress."
                " If you or any of the other assistants have the final answer or deliverable,"
                " prefix your response with FINAL ANSWER so the team knows to stop."
                "Only provide information and assistance related to cloud security. If a query is not related to cloud security, respond with:"
                "I apologize, but I am a specialized chatbot focused solely on cloud security topics. I cannot assist with queries outside this domain. Please try again with a cloud security-related question."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                " You also have access to a set of reference rules for cloud security. Use these rules to guide your analysis and recommendations.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
    return prompt | llm.bind_tools(tools)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    sender: str

def agent_node(state, agent, name):
    result = agent.invoke(state)
    # We convert the agent output into a format that is suitable to append to the global state
    if isinstance(result, ToolMessage):
        pass
    else:
        result = AIMessage(**result.dict(exclude={"type", "name"}), name=name)
    return {
        "messages": [result],
        "sender": name,
    }

def router(state) -> Literal["call_tool", "__end__", "continue"]:
    # This is the router
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        # The previous agent is invoking a tool
        return "call_tool"
    if "FINAL ANSWER" in last_message.content:
        # Any agent decided the work is done
        return "__end__"
    return "continue"

def chunk_json(data, chunk_size=1000):
    """Split JSON data into larger chunks."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

chunks = list(chunk_json(misconfigurations_data))

def is_cloud_security_related(query: str) -> bool:
    """Check if the query is related to cloud security."""
    prompt = PromptTemplate.from_template(
        "Determine if the following query is related to cloud security. "
        "Respond with only 'Yes' or 'No'.\n\nQuery: {query}\nAnswer:"
    )
    chat = ChatGroq(model="llama3-70b-8192")
    chain = prompt | chat
    response = chain.invoke({"query": query})
    return response.content.strip().lower() == "yes"

def process_chunk(chunk, query):
    research_agent = create_agent(
        llm,
        [],
        system_message="""
        Your main job is to analyze the misconfigurations from the provided list and reference rules.
        Determine the severity and suggest remediation steps based on the provided rules.
        If you have sufficient information to provide a meaningful response, include 'FINAL ANSWER:' at the beginning of your message.
        """
    )
    research_node = functools.partial(
        agent_node, agent=research_agent, name="Researcher"
    )

    chart_agent = create_agent(
        llm,
        [],
        system_message="""
        Your main job is to figure out the most important suggestions that need to be applied from the Researcher's plan and display them to the user.
        You have access to the list of misconfigurations in the user's AWS cloud and should use this to make your decision.
        You also have access to a set of reference rules for cloud security. Use these rules to guide your analysis and recommendations.
        If you have sufficient information to provide a meaningful response, include 'FINAL ANSWER:' at the beginning of your message.
        """
    )
    chart_node = functools.partial(agent_node, agent=chart_agent, name="Analyser")

    workflow = StateGraph(AgentState)

    workflow.add_node("Researcher", research_node)
    workflow.add_node("Analyser", chart_node)

    workflow.add_conditional_edges(
        "Researcher",
        router,
        {"continue": "Analyser", "__end__": END},
    )
    workflow.add_conditional_edges(
        "Analyser",
        router,
        {"continue": "Researcher", "__end__": END},
    )

    workflow.add_edge(START, "Researcher")
    graph = workflow.compile()

    try:
        events = graph.stream(
            {
                "messages": [
                    HumanMessage(content=query)
                ],
                "system_message": json.dumps({
                    "misconfigurations": chunk,
                    "reference_rules": reference_rules
                })
            },
            {"recursion_limit": 4},  # Increased from 3 to 4
        )

        res = ""
        for event in events:
            for value in event.values():
                res += value["messages"][-1].content + "\n------------------------------------------------\n"
        
        return res
    except GraphRecursionError:
        # If we hit the recursion limit, return what we have so far
        return "The analysis for this chunk reached the maximum allowed depth. Here's what we gathered:\n" + res

def get_response(query: str):
    if not is_cloud_security_related(query):
        return "I apologize, but I am a specialized chatbot focused solely on cloud security topics. I cannot assist with queries outside this domain. Please try again with a cloud security-related question."

    with ThreadPoolExecutor(max_workers=1000) as executor:
        future_to_chunk = {executor.submit(process_chunk, chunk, query): chunk for chunk in chunks}
        results = []
        for future in as_completed(future_to_chunk):
            try:
                results.append(future.result())
            except Exception as exc:
                print(f'Generated an exception: {exc}')

    combined_results = "\n".join(results)

    template = """You are a helpful assistant whose goal is to summarize the most important suggestions that need to be applied from the input, which is a conversation between two other assistants. Each assistant outputs a block of text with its own suggestions delimited by the string '------------------------------------------------'. Make sure to remove or rephrase all references the assistants make to each other, ensuring that the output is a coherent summary of the most important suggestions with no references to the assistants themselves.

    It is very important that for every suggestion you include in the final output, you also include the relevant CLI commands and action steps that need to be taken to practically implement the suggestion. Make sure that your suggestions are the most important and relevant to the user's AWS cloud configuration.

    Some chunks of analysis may have reached a maximum depth. If you see indications of this, focus on summarizing the available information without speculation about incomplete analysis.

    Begin!

    Input: {messages}
    Summary:"""

    summarise_prompt = PromptTemplate.from_template(template)
    chat = ChatGroq(
        model="llama3-70b-8192",
    )
    chain = summarise_prompt | chat
    summary = chain.invoke({"messages": combined_results})   
    return summary.content