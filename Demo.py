import openai
import re
import streamlit as st
import pandas as pd
import altair as alt
from DemoPrompts import get_system_prompt
from decimal import Decimal  # Import Decimal type

# Function to create Altair chart based on chart type and DataFrame check
def create_altair_chart(chart_type, df):
    if chart_type == 'bar':
        chart = alt.Chart(df).mark_bar().encode(x=df.columns[0], y=df.columns[1], text=alt.Text(df.columns[1], format=',.2f'))
    elif chart_type == 'line':
        chart = alt.Chart(df).mark_line().encode(x=df.columns[0], y=df.columns[1], text=alt.Text(df.columns[1], format=',.2f'))
    elif chart_type == 'area':
        chart = alt.Chart(df).mark_area().encode(x=df.columns[0], y=df.columns[1], text=alt.Text(df.columns[1], format=',.2f'))
    elif chart_type == 'scatter':
        chart = alt.Chart(df).mark_circle().encode(x=df.columns[0], y=df.columns[1], text=alt.Text(df.columns[1], format=',.2f'))
    elif chart_type == 'pie':
        chart = alt.Chart(df).mark_arc().encode(
            theta=df.columns[1],
            color=df.columns[0], text=alt.Text(df.columns[0], format=',.2f')
        )
    else:
        chart = None

    return chart

def match_statement(statement, values):
    matched_value = None
    for val in values:
        if val.lower() in statement.lower():
            matched_value = val
            break
    return matched_value

openai.api_key = st.secrets["OPENAI_API_KEY"]

st.title(":male-detective:	Agent C-Kwell")

conn = st.experimental_connection("snowpark")

# Initialize the chat messages history
if "messages" not in st.session_state:
    # system prompt includes table information, rules, and prompts the LLM to produce a welcome message to the user.
    st.session_state.messages = [{"role": "system", "content": get_system_prompt()}]

# to be used for graph rendering
keywords_to_check = ["pie", "bar", "scatter", "line", "area"]

if "messages" in st.session_state:
    # Prompt for user input and save
    if prompt := st.chat_input():
        st.session_state.messages.append({"role": "user", "content": prompt})

    # display the existing chat messages
    for message in st.session_state.messages:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if "results" in message and "charttype" not in message:
                st.dataframe(message["results"])
            if "charttype" in message:
                charttype = message["charttype"]
                df1 = pd.DataFrame(message["results"])
                df1 = df1.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
                chart_old = create_altair_chart(charttype, df1)
                st.altair_chart(chart_old, use_container_width=True)

    # If last message is not from assistant, we need to generate a new response
    if st.session_state.messages[-1]["role"] != "assistant":
        message_content = st.session_state.messages[-1]["content"]
        with st.chat_message("assistant"):
            response = ""
            resp_container = st.empty()
            for delta in openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                stream=True,
            ):
                response += delta.choices[0].delta.get("content", "")
                resp_container.markdown(response)

            message = {"role": "assistant", "content": response}

            # Parse the response for a SQL query and execute if available
            sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
            if sql_match:
                sql = sql_match.group(1)
                conn = st.experimental_connection("snowpark")
                message["results"] = conn.query(sql)
                # st.write("The answer to your query is")

                # check if user has asked for any type of chart. If a chart type is present render the chart elase display data grid
                contains_keyword = any(keyword in message_content.lower() for keyword in keywords_to_check)
                
                if contains_keyword:
                    chart_type = match_statement(message_content, keywords_to_check)
                    df = pd.DataFrame(message["results"])
                    try:
                        # Convert Decimal type to float for JSON serialization
                        df = df.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
                        chart = create_altair_chart(chart_type, df)
                        if chart is not None:
                            # Convert the Altair chart to a dictionary for serialization
                            # chart_dict = chart.to_dict()
                            message["charttype"] = chart_type
                            st.altair_chart(chart, use_container_width=True)
                        else:
                            st.warning("Unsupported chart type.")
                    except Exception as e:
                        st.error(f"Error creating Altair chart: {e}")
                else:
                    st.dataframe(message["results"])

            st.session_state.messages.append(message)
