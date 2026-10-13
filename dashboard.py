"""Local reviewer dashboard; run `streamlit run dashboard.py`. Not for public hosting."""
from __future__ import annotations

import json
import re
from pathlib import Path

import streamlit as st

from app.config import load_settings
from orchestration.service import WorkflowService

st.set_page_config(page_title='Agentic Engineering Review', layout='wide')
st.title('Agentic Engineering Review')
st.caption('Local operator only • AI-generated code is never automatically executed')
service = WorkflowService(load_settings())

with st.form('start'):
    scenario = st.selectbox('Scenario', ['greenfield', 'brownfield', 'ambiguous'])
    requirement = st.text_area('Custom requirement', height=150, placeholder='Build a Task Management REST API using FastAPI and SQLite...')
    offline = st.checkbox('Offline fixture mode (no API call)')
    submit = st.form_submit_button('Start new workflow')
if submit:
    try:
        result = service.start(scenario, offline=offline, requirement=requirement or None)
        st.session_state['run_id'] = result['run']['run_id']
        st.success('Created run ' + st.session_state['run_id'])
    except Exception as exc:
        st.error(f'Cannot start: {type(exc).__name__}: {exc}')

run_id = st.text_input('Run ID', value=st.session_state.get('run_id', ''))
if run_id:
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        st.error('Invalid run ID')
        st.stop()
    try:
        state, pending = service.state(run_id)
        public = service.store.public_run(run_id)
    except Exception as exc:
        st.error(f'Unable to load run: {type(exc).__name__}: {exc}')
        st.stop()
    st.subheader('Execution status')
    a, b, c = st.columns(3)
    a.metric('Status', public.get('status', '?'))
    b.metric('Revision', public.get('revision', '?'))
    c.metric('Changed files', len(public.get('changed_files') or []))
    st.dataframe(public.get('tasks') or [], use_container_width=True)
    if pending:
        st.warning('Review required: ' + pending['gate'])
        st.code(json.dumps({k: pending[k] for k in ('revision', 'review_hash', 'artifact_names')}, indent=2))
    st.subheader('Artifact review')
    artifact_names = sorted(state.get('artifacts', {}))
    if artifact_names:
        chosen = st.selectbox('Select artifact', artifact_names)
        st.json(state['artifacts'][chosen])
        if chosen in ('implementation_plan', 'repair'):
            for op in state['artifacts'][chosen].get('operations', []):
                for file in op.get('files', []):
                    with st.expander('Proposed source: ' + file['path']):
                        st.code(file['content'], language='python' if file['path'].endswith('.py') else 'markdown')
    if pending:
        with st.form('decision'):
            decision = st.radio('Decision', ['Approve', 'Reject'])
            operator = st.text_input('Operator', value='local-reviewer')
            reason = st.text_input('Reason', placeholder='Reviewed the exact files and risks')
            confirmed = st.checkbox('I reviewed the current artifacts and understand generated code is untrusted')
            sent = st.form_submit_button('Submit gate decision')
        if sent:
            if not confirmed or not reason.strip():
                st.error('Please review and supply a reason before deciding.')
            else:
                try:
                    result = service.resume(run_id, decision == 'Approve', operator, reason, expected_gate=pending['gate'])
                    st.success('Decision saved; refresh to see next stage: ' + result['run']['status'])
                except Exception as exc:
                    st.error(f'Unable to record decision: {type(exc).__name__}: {exc}')
    with st.expander('Revise current requirements or architecture'):
        with st.form('revise'):
            stage = st.selectbox('Stage', ['requirements', 'architecture'])
            revision_text = st.text_area('Revised content')
            revision_reason = st.text_input('Revision reason')
            revised = st.form_submit_button('Request revision')
        if revised:
            try:
                service.revise(run_id, stage, revision_text, 'local-reviewer', revision_reason)
                st.success('Revision recorded; refresh to inspect the updated artifacts')
            except Exception as exc:
                st.error(f'Revision failed: {type(exc).__name__}: {exc}')
    st.subheader('Validation')
    st.json(state.get('validation') or {'status': 'Not run yet'})
    if state.get('custom_generation'):
        st.info('Custom generated code is statically parsed, NOT executed. Run tests only inside a separately hardened sandbox.')
    with st.expander('Change ledger and traceability'):
        st.json({'changes': state.get('artifacts', {}).get('changes', []), 'lineage': state.get('lineage', {}), 'decisions': state.get('decisions', [])})
