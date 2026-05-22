*** Settings ***
Documentation     Swarm coordination integration tests
Library           Collections
Resource          ../resources/common.robot
Resource          ../resources/crdt_keywords.robot

*** Variables ***
@{ROVER_IDS}    rover-sim-1    rover-sim-2    rover-sim-3

*** Test Cases ***
Simulate Three Rover Formation
    [Documentation]    Three rovers should be able to form a line formation
    ${formation}=    Evaluate    __import__('rover_swarm.swarm.formation').FormationController(spacing=5.0)
    ${slots}=    Evaluate    ${formation}.get_slots(3)
    Should Be Equal As Integers    ${len(${slots})}    3
    ${assignments}=    Evaluate    ${formation}.assign_slots(${ROVER_IDS}, __import__('rover_swarm.types').Position(0,0,0))
    Should Be Equal As Integers    ${len(${assignments})}    3
    FOR    ${i}    ${assignment}    IN ENUMERATE    @{assignments}
        ${rover_id}=    Get From List    ${assignment}    0
        Should Be Equal    ${rover_id}    ${ROVER_IDS}[${i}]
    END

Formation Types
    [Documentation]    All formation types should produce correct slot counts
    ${formation}=    Evaluate    __import__('rover_swarm.swarm.formation').FormationController()
    FOR    ${fmt}    IN    LINE    VEE    DIAMOND    WEDGE    COLUMN    CIRCLE    ECHELON_LEFT    ECHELON_RIGHT
        ${fmt_enum}=    Evaluate    __import__('rover_swarm.swarm.formation').FormationType['${fmt}']
        ${formation.set_formation(${fmt_enum})}
        ${slots}=    Evaluate    ${formation}.get_slots(5)
        Should Be Equal As Integers    ${len(${slots})}    5
    END

Task Allocation
    [Documentation]    Tasks should be allocated to available rovers
    ${engine}=    Evaluate    __import__('rover_swarm.swarm.task_allocation').TaskAllocationEngine(node_id='test-leader')
    ${task}=    Evaluate    __import__('rover_swarm.types').Task(task_id='task-1', task_type=__import__('rover_swarm.types').TaskType.EXPLORE)
    ${engine.add_task(${task})}
    ${assignments}=    Evaluate    ${engine}.allocate(['rover-1','rover-2'])
    Should Be Equal As Integers    ${len(${assignments})}    1
    ${first}=    Get From List    ${assignments}    0
    Should Be Equal    ${first.task_id}    task-1

Task Allocation Round Robin
    [Documentation]    Multiple tasks should be allocated in round-robin fashion
    ${engine}=    Evaluate    __import__('rover_swarm.swarm.task_allocation').TaskAllocationEngine()
    FOR    ${i}    IN RANGE    4
        ${task}=    Evaluate    __import__('rover_swarm.types').Task(task_id='task-${i}', task_type=__import__('rover_swarm.types').TaskType.SURVEY)
        ${engine.add_task(${task})}
    END
    ${assignments}=    Evaluate    ${engine}.allocate(['rover-x','rover-y'])
    ${rover_x_count}=    Evaluate    sum(1 for a in ${assignments} if a.rover_id == 'rover-x')
    ${rover_y_count}=    Evaluate    sum(1 for a in ${assignments} if a.rover_id == 'rover-y')
    Should Be Equal As Integers    ${rover_x_count}    2
    Should Be Equal As Integers    ${rover_y_count}    2

Leader Election
    [Documentation]    Raft consensus module should support leader election
    ${node_a}=    Evaluate    __import__('rover_swarm.swarm.consensus').ConsensusModule(node_id='rover-a')
    ${node_b}=    Evaluate    __import__('rover_swarm.swarm.consensus').ConsensusModule(node_id='rover-b')
    ${node_b.receive_heartbeat('rover-a', 1)}
    Should Be True    ${node_b._state.leader_id == 'rover-a'}
    Should Be False    ${node_b.is_leader()}

Leader Election Vote
    [Documentation]    A candidate should request and receive votes
    ${node}=    Evaluate    __import__('rover_swarm.swarm.consensus').ConsensusModule(node_id='rover-master')
    ${granted}=    Evaluate    ${node}.handle_vote_request('rover-candidate', 2)
    Should Be True    ${granted}
    ${count}=    Evaluate    ${node}.handle_vote_response('rover-other')
    Should Be True    ${count} > 1

Gossip Message Propagation
    [Documentation]    Gossip protocol should buffer and disseminate messages
    ${gossip}=    Evaluate    __import__('rover_swarm.swarm.gossip').GossipProtocol(node_id='rover-gossip')
    ${gossip.update_peers(['rover-a','rover-b','rover-c'])}
    ${gossip.gossip({'type': 'test', 'data': 'hello'})}
    ${stats}=    Evaluate    ${gossip}.stats()
    Should Be Equal As Integers    ${stats['peers']}    3
    Should Be Equal As Integers    ${stats['buffer_size']}    1
