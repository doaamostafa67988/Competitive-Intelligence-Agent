"""
Interactive graph visualization (bonus feature) so leadership can explore
Competitor -> Product -> PricePoint -> Announcement relationships directly.
"""
import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import api_client as api

st.set_page_config(page_title="Knowledge Graph", page_icon="🕸️", layout="wide")
st.title("🕸️ Competitor Knowledge Graph")

try:
    edges = api.graph_snapshot()
except Exception as e:
    st.warning(f"Could not reach backend: {e}")
    edges = []

if not edges:
    st.info("Graph is empty — run the pipeline from the Dashboard page first.")
else:
    G = nx.DiGraph()
    for e in edges:
        G.add_edge(e["from_key"], e["to_key"], rel_type=e["rel_type"])

    pos = nx.spring_layout(G, seed=42, k=0.6)

    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(x=edge_x, y=edge_y, line=dict(width=1, color="#888"), hoverinfo="none", mode="lines")

    node_x = [pos[n][0] for n in G.nodes()]
    node_y = [pos[n][1] for n in G.nodes()]
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text", text=list(G.nodes()), textposition="top center",
        hoverinfo="text",
        marker=dict(size=16, color="#2563eb", line=dict(width=1, color="white")),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=650,
                       xaxis=dict(showgrid=False, zeroline=False, visible=False),
                       yaxis=dict(showgrid=False, zeroline=False, visible=False))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Ask the graph")
    default_q = "MATCH (c:Competitor)-[r]->(n) RETURN c.key AS competitor, type(r) AS relationship, n.key AS target LIMIT 25"
    cypher = st.text_area("Cypher query (read-only)", value=default_q, height=100)
    if st.button("Run query"):
        with st.spinner("Querying Neo4j..."):
            try:
                import httpx, os
                base = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1")
                resp = httpx.post(f"{base}/graph/query", json={"cypher": cypher}, timeout=60)
                resp.raise_for_status()
                st.dataframe(resp.json(), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Query failed: {e}")
