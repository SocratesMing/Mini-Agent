import sqlite3
import json

conn = sqlite3.connect('data/mini_agent.db')
cursor = conn.cursor()

cursor.execute('SELECT session_id, messages FROM sessions ORDER BY updated_at DESC LIMIT 3')
rows = cursor.fetchall()

for r in rows:
    session_id = r[0]
    messages = json.loads(r[1])
    print(f"\n{'='*60}")
    print(f"Session: {session_id}")
    print(f"Messages count: {len(messages)}")
    
    if messages:
        last_msg = messages[-1]
        print(f"Last message role: {last_msg.get('role')}")
        print(f"Last message content length: {len(last_msg.get('content', ''))}")
        thinking = last_msg.get('thinking')
        if thinking:
            print(f"Thinking length: {len(thinking)}")
            print(f"Thinking preview: {thinking[:200]}...")
        else:
            print("Thinking: None")
        
        blocks = last_msg.get('blocks', [])
        print(f"Blocks count: {len(blocks)}")
        for i, block in enumerate(blocks):
            print(f"  Block {i}: type={block.get('type')}")
            if block.get('type') == 'thinking':
                print(f"    Thinking content: {block.get('content', '')[:100]}...")
        
        print(f"\nFull message keys: {list(last_msg.keys())}")

conn.close()
