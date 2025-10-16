"""
agents.py

This module defines the LangChain agents for the multi-agent trading system.
Each agent is configured with specific tools and a role, working together to
automate the trading process.
"""

import json
import logging
import os
import vertexai
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.prompts import PromptTemplate
from langchain_google_vertexai import ChatVertexAI
from langchain_ollama import ChatOllama
import asyncio
import io
from langchain_core.callbacks import StdOutCallbackHandler
from contextlib import redirect_stdout, redirect_stderr
import concurrent.futures

from utils import is_market_open

from tools import (
    get_stock_data_tool,
    get_llm_analysis_tool,
    run_monte_carlo_tool,
    execute_trade_tool,
    get_portfolio_status_tool,
)

# --- Agent Configuration ---

# Initialize Vertex AI. You must set GOOGLE_CLOUD_PROJECT in your .env file.
try:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
    vertexai.init(project=project_id)
    logging.info(f"Vertex AI initialized for project: {project_id}")
except Exception as e:
    logging.critical(f"Failed to initialize Vertex AI: {e}")
    # The application will likely fail below, but this provides a clear starting error.

# LLM is now initialized inside the run_analyst_for_stock function
# to ensure it's created correctly in each worker process.

# --- Tool Definitions ---
# Wrap the functions in Tool objects for the agents to use

data_aggregator_tools = [
    Tool(
        name="get_stock_data_tool",
        func=get_stock_data_tool,
        description="""Fetches and aggregates fundamental data, news, and price action for a given stock ticker from Polygon.io. This is the primary tool for data collection."""
    )
]

analyst_tools = [
    Tool(
        name="get_llm_analysis_tool",
        func=get_llm_analysis_tool,
        description="""Performs analysis on a single stock's data using the best available LLM. It should be called for each stock individually."""
    ),
    Tool(
        name="run_monte_carlo_tool",
        func=run_monte_carlo_tool,
        description="""Takes a list of stocks that have received a 'BUY' recommendation and runs a Monte Carlo simulation to determine the single best stock to trade based on risk-adjusted returns."""
    )
]

portfolio_manager_tools = [
    Tool(
        name="execute_trade_tool",
        func=execute_trade_tool,
        description="""Executes a trade (BUY or SELL) for a given stock ticker through Interactive Brokers. This is a critical, privileged tool."""
    ),
    Tool(
        name="get_portfolio_status_tool",
        func=get_portfolio_status_tool,
        description="""Retrieves the current portfolio status from Interactive Brokers, including all current positions and account values."""
    )
]


# --- 1. Data Aggregator Agent ---

data_aggregator_prompt_template = """
You are a Data Aggregator Agent. Your sole responsibility is to gather comprehensive data for a given stock ticker.
You must use the 'get_stock_data_tool' to fetch this data. Do not perform any analysis or make any decisions.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

data_aggregator_prompt = PromptTemplate.from_template(data_aggregator_prompt_template)

# This agent is not used in the parallel workflow and is being removed
# to resolve the NameError for the globally defined 'llm'.
# data_aggregator_agent = create_react_agent(
#     llm=llm,
#     tools=data_aggregator_tools,
#     prompt=data_aggregator_prompt
# )

# data_aggregator_executor = AgentExecutor(
#     agent=data_aggregator_agent,
#     tools=data_aggregator_tools,
#     verbose=True,
#     handle_parsing_errors=True
# )

# --- 1. Analyst Agent Prompt ---
# This prompt is designed to be very strict to prevent "lazy" agent behavior.
analyst_prompt = PromptTemplate.from_template("""
You are a meticulous Financial Analyst Agent. Your primary and ONLY goal is to analyze the provided data for a single stock and produce a clear, actionable trading recommendation.

**CRITICAL INSTRUCTIONS:**
1.  You MUST output a JSON object.
2.  Your output MUST contain the following three fields: "decision", "confidence", and "reasoning".
3.  The "decision" must be one of three strings: "BUY", "SELL", or "HOLD".
4.  The "confidence" must be a float between 0.0 and 1.0, representing your certainty in the decision.
5.  The "reasoning" must be a detailed, multi-sentence explanation justifying your decision based on the provided data.
6.  You are FORBIDDEN from simply returning the input data. Your task is to ADD the analysis fields to the data. Any output that does not contain "decision", "confidence", and "reasoning" is a failure.

**INPUT DATA:**
{input}

**TOOLS:**
You have access to the following tools. Use them to perform your analysis.
{tools}

**TOOL NAMES:**
{tool_names}

**ANALYSIS PROCESS:**
{agent_scratchpad}

**FINAL JSON OUTPUT:**
""")


# --- Agent Definitions ---

def create_analyst_agent(llm, tools):
    """Creates the Analyst Agent."""
    return create_react_agent(llm, tools, analyst_prompt)


# --- DEPRECATED AGENTS (To be removed or refactored) ---

# The old prompts are kept here for reference but are no longer used by the primary analyst agent.
# They will be removed in a future cleanup.

# --- 1. Data Aggregator Agent ---

data_aggregator_prompt_template = """
You are a Data Aggregator Agent. Your sole responsibility is to gather comprehensive data for a given stock ticker.
You must use the 'get_stock_data_tool' to fetch this data. Do not perform any analysis or make any decisions.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final output from the tool

Begin!

Question: {input}
{agent_scratchpad}
"""

# --- 2. Analyst Agent (OLD) ---

analyst_prompt_template_old = """
You are a Financial Analyst Agent. Your goal is to provide a 'BUY', 'SELL', or 'HOLD' recommendation for a given stock.
You will be given a JSON object containing the stock's ticker, fundamental data, and recent news.
Analyze this information and provide a recommendation. Your final answer must be a JSON object containing the original data plus your analysis.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: a JSON object with your recommendation

Begin!

Question: {input}
{agent_scratchpad}
"""

# --- 3. Portfolio Manager Agent ---

portfolio_manager_prompt_template = """
You are a Portfolio Manager Agent. You are responsible for executing trades and managing the portfolio.
You will receive a single stock recommendation with a 'BUY' decision. Your job is to execute this trade.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: a summary of the trade execution status

Begin!

Question: {input}
{agent_scratchpad}
"""

# --- Agent Executors (OLD - To be refactored) ---
# These are constructed using the old prompts and will be updated or removed.

data_aggregator_prompt = PromptTemplate(
    input_variables=["input", "tools", "tool_names", "agent_scratchpad"],
    template=data_aggregator_prompt_template,
)
# data_aggregator_agent = create_react_agent(llm, data_aggregator_tools, data_aggregator_prompt)
# data_aggregator_executor = AgentExecutor(agent=data_aggregator_agent, tools=data_aggregator_tools, verbose=True)

analyst_prompt_old = PromptTemplate(
    input_variables=["input", "tools", "tool_names", "agent_scratchpad"],
    template=analyst_prompt_template_old,
)
# analyst_agent = create_react_agent(llm, analyst_tools, analyst_prompt)
# analyst_executor = AgentExecutor(agent=analyst_agent, tools=analyst_tools, verbose=True, handle_parsing_errors=True)


portfolio_manager_prompt = PromptTemplate(
    input_variables=["input", "tools", "tool_names", "agent_scratchpad"],
    template=portfolio_manager_prompt_template,
)
# portfolio_manager_agent = create_react_agent(llm, portfolio_manager_tools, portfolio_manager_prompt)
# portfolio_manager_executor = AgentExecutor(agent=portfolio_manager_agent, tools=portfolio_manager_tools, verbose=True)


# --- Agent Execution Logic ---

def run_analyst_for_stock(stock_data: dict, worker_id: int) -> dict:
    """
    Runs the Analyst Agent for a single stock.
    This function is designed to be executed in a separate process.
    It captures and returns the agent's final analysis.
    """
    # --- Setup per-worker logging to a dedicated file ---
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file_path = os.path.join(log_dir, f'analyst_worker_{worker_id}.log')
    
    # Configure a logger specific to this worker
    worker_log_name = f'analyst_worker_{worker_id}'
    worker_logger = logging.getLogger(worker_log_name)
    worker_logger.setLevel(logging.INFO)
    worker_logger.propagate = False
    
    # Clear existing handlers and add a file handler
    if worker_logger.hasHandlers():
        worker_logger.handlers.clear()
        
    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setFormatter(logging.Formatter(f'%(asctime)s - [Analyst-{worker_id}] - %(message)s'))
    worker_logger.addHandler(file_handler)

    # Also capture stdout/stderr to log agent's internal thoughts
    stdout_capture = io.StringIO()

    worker_logger.info(f"Starting analysis for ticker: {stock_data.get('ticker', 'N/A')}")

    # --- Agent and Prompt Definition ---
    # This prompt now guides the agent's entire thinking process.
    analyst_prompt = PromptTemplate(
        template="""
        You are a meticulous Financial Analyst Agent. Your goal is to produce a detailed, evidence-based analysis for a single stock.

        **Rules of Engagement:**
        1.  You MUST use the `get_llm_analysis_tool` to perform the core analysis.
        2.  Do not make up data. Your analysis is based *only* on the data provided to the tool.
        3.  Your final answer must be the direct, unmodified JSON output from the `get_llm_analysis_tool`.

        **TOOLS:**
        ------
        You have access to the following tools:
        {tools}

        **TOOL NAMES:**
        {tool_names}

        **PROCEDURE:**
        To answer the question, you must use the following format:
        ```
        Thought: Do I need to use a tool? Yes. I must use the `get_llm_analysis_tool` to analyze the stock.
        Action: The tool to use, which is always `get_llm_analysis_tool`.
        Action Input: The JSON data for the stock to be analyzed.
        Observation: The JSON result from the `get_llm_analysis_tool`.
        Thought: I have received the analysis. I now have my final answer.
        Final Answer: The complete JSON output from the 'Observation' step.
        ```

        **START ANALYSIS:**

        Question: Analyze the following stock data and provide a 'BUY' or 'HOLD' recommendation.
        Stock Data: {input}
        {agent_scratchpad}
        """,
        input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
    )

    # --- LLM and Agent Initialization ---
    # The LLM is defined here to be process-safe.
    # For this agent, we use Gemini as it's fast and suitable for ReAct prompting.
    try:
        llm = ChatVertexAI(model_name="gemini-2.5-flash")
        
        # Create the ReAct Agent
        analyst_agent = create_react_agent(llm, analyst_tools, analyst_prompt)
        agent_executor = AgentExecutor(
            agent=analyst_agent,
            tools=analyst_tools,
            verbose=True, # This is key for capturing the thought process
            handle_parsing_errors=True
        )
    except Exception as e:
        worker_logger.error(f"Failed to initialize agent or LLM: {e}")
        # Print logs and return error
        worker_logger.error(f"Failed to initialize agent or LLM: {e}")
        return {"decision": "ERROR", "reasoning": f"Agent initialization failed: {e}"}

    # --- Execute the Agent and Capture Output ---
    try:
        # The `with` statements redirect stdout/stderr to capture the agent's verbose output
        with redirect_stdout(stdout_capture), redirect_stderr(stdout_capture):
            # The handler prints the captured output with the worker prefix
            handler = StdOutCallbackHandler()
            result = agent_executor.invoke(
                {"input": json.dumps(stock_data), "tools": ", ".join([t.name for t in analyst_tools]), "tool_names": ", ".join([t.name for t in analyst_tools])},
                callbacks=[handler]
            )
        
        # --- Process and Return Result ---
        # The actual analysis is in the 'output' key of the agent's result
        final_analysis_str = result.get('output', '{}')
        final_analysis = json.loads(final_analysis_str)

        worker_logger.info(f"Successfully completed analysis for {stock_data.get('ticker', 'N/A')}.")
        worker_logger.info(f"--- Agent Trace --- \n{stdout_capture.getvalue()}")

        return final_analysis

    except Exception as e:
        worker_logger.error(f"An error occurred during agent execution: {e}", exc_info=True)
        worker_logger.error(f"--- Agent Trace --- \n{stdout_capture.getvalue()}")
        return {"decision": "ERROR", "reasoning": str(e)}

from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish

class CustomLoggerCallbackHandler(BaseCallbackHandler):
    """Custom callback handler that logs agent actions to a specific logger."""
    def __init__(self, logger, ticker):
        self.logger = logger
        self.ticker = ticker

    def on_agent_action(self, action: AgentAction, **kwargs) -> None:
        """Log the agent's action."""
        self.logger.info(f"[{self.ticker}] Thought: {action.log.strip()}")

    def on_tool_end(self, output: str, **kwargs) -> None:
        """Log the tool's output."""
        self.logger.info(f"[{self.ticker}] Observation: {output.strip()}")

    def on_agent_finish(self, finish: AgentFinish, **kwargs) -> None:
        """Log the agent's final answer."""
        self.logger.info(f"[{self.ticker}] Final Answer: {finish.log.strip()}")
