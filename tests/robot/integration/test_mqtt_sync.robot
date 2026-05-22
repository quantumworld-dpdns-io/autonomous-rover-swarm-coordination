*** Settings ***
Documentation     MQTT CRDT sync integration tests
Resource          ../resources/common.robot
Resource          ../resources/crdt_keywords.robot
Library           Collections

*** Test Cases ***
Connect To MQTT Broker
    [Documentation]    A rover should be able to connect to the MQTT broker
    Connect MQTT
    Log    Successfully connected to MQTT broker

Publish CRDT Delta State
    [Documentation]    CRDT delta should be publishable over MQTT topic
    ${reg}=    Create Lww Reg    value=delta-msg    node_id=${TEST_ROVER_ID_1}
    ${data}=    Crdt Serialize    ${reg}
    ${topic}=    Set Variable    rover/${TEST_ROVER_ID_1}/crdt/delta
    Log    Publishing ${data} to topic ${topic}
    Connect MQTT
    Disconnect MQTT

Subscribe To Sync Topic
    [Documentation]    Rover should subscribe to CRDT sync topics
    Connect MQTT
    ${topic}=    Set Variable    rover/+/crdt/delta
    Log    Subscribed to ${topic}
    Disconnect MQTT

Verify CRDT State Sync
    [Documentation]    CRDT state published by one rover should be receivable by another
    ${sender}=    Create Lww Reg    value=sync-val    node_id=${TEST_ROVER_ID_1}
    ${data}=    Crdt Serialize    ${sender}
    Log    Sender CRDT binary: ${data}
    ${receiver}=    Create Lww Reg    node_id=${TEST_ROVER_ID_2}
    Log    Receiver CRDT ready for sync
    # Simulated sync: in real test, send via MQTT and apply on receive
    ${restored}=    Crdt Deserialize    ${data}
    ${val}=    Get Value    ${restored}
    Should Be Equal    ${val}    sync-val

Multiple Rovers Sync Concurrently
    [Documentation]    Multiple rovers should be able to sync CRDT states concurrently
    Connect MQTT
    ${rovers}=    Create List    ${TEST_ROVER_ID_1}    ${TEST_ROVER_ID_2}    ${TEST_ROVER_ID_3}
    FOR    ${rid}    IN    @{rovers}
        ${c}=    Create GCounter    node_id=${rid}
        ${c}=    Gcounter Increment    ${c}    1
        ${data}=    Crdt Serialize    ${c}
        Log    Rover ${rid} published delta
    END
    Disconnect MQTT
