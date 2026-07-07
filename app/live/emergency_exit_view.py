class EmergencyExitView:

    @staticmethod
    def show(data):
        if data["action"] == "EMERGENCY":
            print()
            print("!" * 60)
            print("EMERGENCY EXIT")
            print("!" * 60)
            print(f"Type   : {data.get('emergency_type', 'UNKNOWN')}")
            print(f"Reason : {data['reason']}")
            print(f"Ticket : {data['ticket']}")
