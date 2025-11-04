import discord

class ContribuirView(discord.ui.View):
    def __init__(self):
        super().__init__()
        
        self.add_item(
            discord.ui.Button(
                label="Doar pelo PayPal",
                url="https://www.paypal.com/donate/?hosted_button_id=25EPVUVQK4FR4"
            )
        )
