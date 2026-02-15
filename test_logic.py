numbers = [10, 5, 0, 2]

for num in numbers:
    # This will crash when it hits 0
    result = 100 / num
    print(f"Result is {result}")
