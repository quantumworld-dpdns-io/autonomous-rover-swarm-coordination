*** Settings ***
Documentation     API integration tests for rover swarm REST endpoints
Library           RequestsLibrary
Library           Collections
Resource          ../resources/common.robot

*** Variables ***
${AUTH_TOKEN}            ${EMPTY}

*** Keywords ***
Authenticate As Admin
    [Documentation]    Obtain an admin JWT token
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${ADMIN_USERNAME}", "password": "${ADMIN_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    Set Suite Variable    ${AUTH_TOKEN}    ${token}
    RETURN    ${token}

Authenticate As Observer
    [Documentation]    Obtain an observer JWT token
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${OBSERVER_USERNAME}", "password": "${OBSERVER_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    RETURN    ${token}

*** Test Cases ***
Health Endpoint Returns OK
    [Documentation]    /health should return 200 with status
    API Health Should Be OK

Create Mission
    [Documentation]    Authenticated user should be able to create a mission
    ${token}=    Authenticate As Admin
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    POST On Session    api    /missions
    ...    json={"mission_id": "${TEST_MISSION_ID}", "name": "Test Mission"}
    ...    headers=${headers}
    ...    expected_status=201
    Should Be Equal As Strings    ${resp.status_code}    201

List Rovers
    [Documentation]    Should list all rovers in the swarm
    ${token}=    Authenticate As Admin
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    GET On Session    api    /rovers    headers=${headers}    expected_status=200
    Should Be Equal As Strings    ${resp.status_code}    200
    ${rovers}=    Set Variable    ${resp.json()}
    Log    Found rovers: ${rovers}

Send Command
    [Documentation]    Should send a command to a specific rover
    ${token}=    Authenticate As Admin
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    POST On Session    api    /rovers/${TEST_ROVER_ID_1}/command
    ...    json={"command": "move", "params": {"x": 10, "y": 20}}
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Equal As Strings    ${resp.status_code}    200

Auth Login Flow
    [Documentation]    Unauthenticated requests to protected endpoints should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    GET On Session    api    /rovers    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

Auth Refresh Token
    [Documentation]    Should be able to refresh an access token
    ${token}=    Authenticate As Admin
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    POST On Session    api    /auth/refresh
    ...    headers=${headers}
    ...    expected_status=200
    Should Contain    ${resp.json()}    access_token

Role Based Access Control
    [Documentation]    Observer should not be able to create missions
    ${token}=    Authenticate As Observer
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    POST On Session    api    /missions
    ...    json={"mission_id": "test-2", "name": "Should Fail"}
    ...    headers=${headers}
    ...    expected_status=403
    Should Be Equal As Strings    ${resp.status_code}    403
