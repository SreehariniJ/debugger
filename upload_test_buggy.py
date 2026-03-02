
def calculate_factorial(n):
    if n < 0:
        return "Error: Negative input"
    # Bug here: name error and logic issue
    res = 1
    for i in range(1, m + 1):
        res *= i
    return res

class DataProcessor:
    def __init__(self, data):
        self.data = data
    
    def process(self):
        # Bug here: division by zero
        if not self.data:
            return 100 / 0
        return sum(self.data) / len(self.data)

if __name__ == "__main__":
    print(calculate_factorial(5))
    dp = DataProcessor([])
    print(dp.process())
